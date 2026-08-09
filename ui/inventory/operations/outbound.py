import streamlit as st
import pandas as pd
from datetime import datetime
from hashlib import sha1
from zoneinfo import ZoneInfo

from db.inventory import SIZE_COLUMNS, apply_adjustment_rows, normalize_adjustment_rows
from db.inventory.operations.outbound import (
    OUTBOUND_SPECS,
    apply_outbound_batch_date,
    build_outbound_sku_lookup,
    build_temporary_shortage_adjustments,
    build_outbound_package_template,
    convert_packages_to_adjustments,
    convert_sku_package_entries,
    load_container_outbound_specs,
    load_sku_outbound_specs,
    normalize_outbound_packages,
)
from db.inventory.master_data.repository import load_sku_catalog
from db.inventory.operations.outbound_audit import (
    audit_outbound_batch,
    find_outbound_inventory_issues,
    load_outbound_inventory,
)
from ui.inventory.i18n import get_language
from ui.inventory.operations.outbound_feedback import (
    render_outbound_audit,
    render_outbound_preview_summary,
    store_outbound_audit_feedback,
)
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from ui.inventory.operations.outbound_status import finish_daily_outbound_backfill
from ui.inventory.operations.packaging_rules import (
    render_packaging_rule_editor,
)
from ui.inventory.operations.outbound_i18n import (
    COLUMNS,
    COLORS,
    TEXT,
    to_display_table,
    to_internal_table,
    translate_package,
)
from utils.auth import get_current_operator_name
from utils.sku_sorting import sort_sku_rows


SKU_ENTRY_TEXT = {
    "zh": {
        "title": "按 SKU 和箱规录入",
        "help": "只添加实际出库的 SKU；填写箱数或包数后，下方直接显示换算总件数。",
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "size": "尺码",
        "package": "包装单位",
        "units": "箱规（件数）",
        "units_help": "可留空使用换算规则；同一 SKU 有 70/72 件箱规时请直接填写。",
        "count": "箱数 / 包数",
        "total": "总件数",
        "total_help": "根据箱规和箱数 / 包数自动计算，不可手动修改。",
        "packages": {"Box": "箱", "Bag": "包"},
        "import_title": "批量文件导入（可选）",
    },
    "en": {
        "title": "Enter by SKU and pack size",
        "help": "Add only outbound SKUs. The converted piece total appears below.",
        "brand": "Brand", "material": "Material",
        "color": "Color", "size": "Size",
        "package": "Package",
        "units": "Pieces per package",
        "units_help": "Leave blank for the conversion rule, or enter an exact pack size.",
        "count": "Boxes / bags",
        "total": "Total pieces",
        "total_help": "Calculated automatically from pack size and package count.",
        "packages": {"Box": "Box", "Bag": "Bag"},
        "import_title": "Batch file import (optional)",
    },
    "es": {
        "title": "Registrar por SKU y empaque",
        "help": "Agregue solo los SKU enviados; el total convertido aparece abajo.",
        "brand": "Marca", "material": "Material",
        "color": "Color", "size": "Talla",
        "package": "Empaque",
        "units": "Piezas por empaque",
        "units_help": "Déjelo vacío para usar la regla o indique el empaque exacto.",
        "count": "Cajas / bolsas",
        "total": "Piezas totales",
        "total_help": "Se calcula automáticamente según el empaque y la cantidad.",
        "packages": {"Box": "Caja", "Bag": "Bolsa"},
        "import_title": "Importación por archivo (opcional)",
    },
}


def render_daily_outbound(supabase, department, category):
    language = get_language()
    text = TEXT[language]
    st.subheader(text["title"])
    st.warning(text["notice"])
    temporary_saved_message = st.session_state.pop(
        "daily_outbound_temporary_saved_message", None
    )
    if temporary_saved_message:
        st.success(temporary_saved_message)

    if st.session_state.pop("daily_outbound_reset_date", False):
        st.session_state.pop("daily_outbound_batch_date", None)
    version = st.session_state.get("daily_outbound_version", 0)
    container_specs = load_container_outbound_specs(
        supabase, department, category
    )
    existing_specs = {**container_specs, **OUTBOUND_SPECS}
    sku_specs = load_sku_outbound_specs(
        supabase, department, category, existing_specs
    )
    outbound_specs = {**container_specs, **sku_specs, **OUTBOUND_SPECS}
    specs_signature = outbound_specs_signature(outbound_specs)
    sku_df = load_sku_catalog(supabase, department, active_only=True)
    if category and not sku_df.empty:
        sku_df = sku_df[sku_df["category"] == category]
    sku_lookup = build_outbound_sku_lookup(sku_df)
    movement_date = st.date_input(
        text["batch_date"],
        value=st.session_state.get(
            "inventory_today",
            datetime.now(ZoneInfo("America/New_York")).date(),
        ),
        key="daily_outbound_batch_date",
    )
    with st.expander(text["rules_title"], expanded=False):
        st.info(text["rules_help"])
        packaging_rules, sku_packaging_rules = render_packaging_rule_editor(
            supabase,
            department,
            category,
            language,
            sku_df=sku_df,
        )

    entry_text = SKU_ENTRY_TEXT[language]
    sku_values = list(sku_lookup.values())
    brands = sorted({value["brand"] for value in sku_values})
    materials = sorted({value["material"] for value in sku_values})
    available_colors = {value["color"] for value in sku_values}
    colors = [value for value in ["黑", "白"] if value in available_colors]
    colors.extend(sorted(available_colors - set(colors)))
    available_sizes = {value["size"] for value in sku_values}
    sizes = [value for value in SIZE_COLUMNS if value in available_sizes]
    sizes.extend(sorted(available_sizes - set(sizes)))
    st.markdown(f"**{entry_text['title']}**")
    st.caption(entry_text["help"])
    package_labels = entry_text["packages"]
    entry_state_key = (
        f"daily_outbound_sku_source_{language}_{version}_"
        f"{movement_date.isoformat()}"
    )
    entry_table_version_key = f"{entry_state_key}_table_version"
    entry_source = pd.DataFrame(
        st.session_state.get(entry_state_key, [{
            entry_text["brand"]: None,
            entry_text["material"]: None,
            entry_text["color"]: None,
            entry_text["size"]: None,
            entry_text["package"]: package_labels["Box"],
            entry_text["units"]: None,
            entry_text["count"]: 0,
            entry_text["total"]: 0,
        }])
    )
    entry_display_df = st.data_editor(
        entry_source,
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        disabled=[entry_text["total"]],
        column_config={
            entry_text["brand"]: st.column_config.SelectboxColumn(
                entry_text["brand"], options=brands, required=True,
            ),
            entry_text["material"]: st.column_config.SelectboxColumn(
                entry_text["material"], options=materials, required=True,
            ),
            entry_text["color"]: st.column_config.SelectboxColumn(
                entry_text["color"], options=colors, required=True,
            ),
            entry_text["size"]: st.column_config.SelectboxColumn(
                entry_text["size"], options=sizes, required=True,
            ),
            entry_text["package"]: st.column_config.SelectboxColumn(
                entry_text["package"],
                options=list(package_labels.values()),
                required=True,
            ),
            entry_text["units"]: st.column_config.NumberColumn(
                entry_text["units"], min_value=1, step=1, format="%d",
                help=entry_text["units_help"],
            ),
            entry_text["count"]: st.column_config.NumberColumn(
                entry_text["count"], min_value=0, step=1, format="%d",
                required=True,
            ),
            entry_text["total"]: st.column_config.NumberColumn(
                entry_text["total"], min_value=0, format="%d",
                help=entry_text["total_help"],
            ),
        },
        key=(
            f"daily_outbound_sku_editor_{language}_{version}_"
            f"{movement_date.isoformat()}_{len(sku_lookup)}_"
            f"{specs_signature}_"
            f"{st.session_state.get(entry_table_version_key, 0)}"
        ),
    )
    entry_df = entry_display_df.rename(columns={
        entry_text["brand"]: "品牌",
        entry_text["material"]: "材质",
        entry_text["color"]: "颜色",
        entry_text["size"]: "尺码",
        entry_text["package"]: "包装单位",
        entry_text["units"]: "箱规",
        entry_text["count"]: "包装数量",
        entry_text["total"]: "换算件数",
    })
    reverse_packages = {
        label: package_type for package_type, label in package_labels.items()
    }
    entry_df["包装单位"] = entry_df["包装单位"].map(
        reverse_packages
    ).fillna("Box")
    adjustment_df, package_preview_df = convert_sku_package_entries(
        entry_df,
        sku_lookup,
        movement_date,
        packaging_rules,
        sku_packaging_rules,
    )
    calculated_totals = []
    for _, entry_row in entry_df.iterrows():
        _, row_preview = convert_sku_package_entries(
            pd.DataFrame([entry_row]),
            sku_lookup,
            movement_date,
            packaging_rules,
            sku_packaging_rules,
        )
        calculated_totals.append(
            int(row_preview.iloc[0]["总件数"])
            if not row_preview.empty else 0
        )
    displayed_totals = pd.to_numeric(
        entry_df["换算件数"], errors="coerce"
    ).fillna(0).astype(int).tolist()
    if displayed_totals != calculated_totals:
        refreshed_source = entry_display_df.copy()
        refreshed_source[entry_text["total"]] = calculated_totals
        st.session_state[entry_state_key] = refreshed_source.to_dict("records")
        st.session_state[entry_table_version_key] = (
            int(st.session_state.get(entry_table_version_key, 0)) + 1
        )
        st.rerun()
    package_preview_df = sort_sku_rows(
        package_preview_df,
        material="材质",
        color="颜色",
        size="尺码",
        leading=["品牌"],
    )

    with st.expander(entry_text["import_title"], expanded=False):
        date_column = COLUMNS[language]["日期"]
        template_df = to_display_table(
            build_outbound_package_template(outbound_specs), language
        ).drop(columns=[date_column])
        st.download_button(
            text["download"],
            data=template_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=text["file"],
            mime="text/csv",
            width="stretch",
        )
        uploaded_file = st.file_uploader(
            text["upload"],
            type=["xlsx", "xls", "csv"],
            key=(
                f"daily_outbound_upload_{language}_{version}_"
                f"{movement_date.isoformat()}"
            ),
        )
        if uploaded_file is not None:
            try:
                upload_df = (
                    pd.read_csv(uploaded_file)
                    if uploaded_file.name.lower().endswith(".csv")
                    else pd.read_excel(uploaded_file)
                )
                upload_df = normalize_outbound_packages(
                    apply_outbound_batch_date(
                        to_internal_table(upload_df, language), movement_date
                    ),
                    outbound_specs,
                )
                uploaded_adjustments = convert_packages_to_adjustments(
                    upload_df,
                    packaging_rules,
                    sku_packaging_rules,
                    outbound_specs,
                )
                adjustment_df = pd.concat(
                    [adjustment_df, uploaded_adjustments], ignore_index=True
                )
            except Exception as error:
                st.error(f"{text['read_error']}: {error}")
                return
    if adjustment_df.empty:
        st.info(text["empty"])
        return

    st.markdown(f"#### {text['preview']}")
    if not package_preview_df.empty:
        display_preview = package_preview_df.copy()
        display_preview["包装单位"] = display_preview["包装单位"].map(
            package_labels
        )
        display_preview = display_preview.rename(columns={
            "品牌": entry_text["brand"],
            "材质": entry_text["material"],
            "颜色": entry_text["color"],
            "尺码": entry_text["size"],
            "包装单位": entry_text["package"],
            "箱规": entry_text["units"],
            "包装数量": entry_text["count"],
            "总件数": entry_text["total"],
        })
        st.dataframe(display_preview, hide_index=True, width="stretch")
    adjustment_df = normalize_adjustment_rows(adjustment_df)
    if adjustment_df.empty:
        st.warning(text["empty"])
        return
    total = render_outbound_preview_summary(adjustment_df, text)
    try:
        inventory_df = load_outbound_inventory(
            supabase, department, category
        )
        inventory_issues = find_outbound_inventory_issues(
            adjustment_df, inventory_df
        )
    except Exception as error:
        st.error(f"{text['inventory_check_error']}: {error}")
        return
    render_inventory_change_comparison(
        build_inventory_change_comparison(inventory_df, adjustment_df),
        action="扣减",
    )
    if not inventory_issues.empty:
        st.error(text["inventory_issue"])
        st.dataframe(
            inventory_issues,
            hide_index=True,
            width="stretch",
            column_config={
                "数量": st.column_config.NumberColumn(
                    text["outbound_quantity"], format="%d"
                ),
                "当前库存": st.column_config.NumberColumn(
                    text["current_inventory"], format="%d"
                ),
                "缺口": st.column_config.NumberColumn(
                    text["shortage"], format="%d"
                ),
            },
        )
        st.info(text["inventory_issue_help"])
        temporary_rows = build_temporary_shortage_adjustments(
            inventory_issues, movement_date
        )
        missing_sku_count = int(
            (inventory_issues["问题"] == "SKU 不存在").sum()
        )
        if missing_sku_count:
            st.warning(
                text["missing_sku_help"].format(count=missing_sku_count)
            )
        if not temporary_rows.empty:
            with st.expander(text["temporary_title"], expanded=True):
                st.caption(text["temporary_help"])
                st.dataframe(
                    temporary_rows[
                        ["品牌", "材质", "颜色", "尺码", "数量"]
                    ],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "数量": st.column_config.NumberColumn(
                            text["temporary_quantity"], format="%d"
                        ),
                    },
                )
                if st.button(
                    text["temporary_confirm"],
                    width="stretch",
                    type="primary",
                    key="daily_outbound_fill_shortage",
                ):
                    try:
                        apply_adjustment_rows(
                            supabase,
                            department,
                            category,
                            temporary_rows,
                            get_current_operator_name(),
                            source_type="transfer",
                        )
                    except Exception as error:
                        st.error(f"{text['temporary_failed']}: {error}")
                        return
                    st.session_state[
                        "daily_outbound_temporary_saved_message"
                    ] = text["temporary_saved"].format(
                        count=len(temporary_rows),
                        quantity=int(temporary_rows["数量"].sum()),
                    )
                    st.rerun()
        return
    st.warning(text["unsaved"])
    if not st.button(
        text["confirm"], width="stretch", type="primary"
    ):
        return

    username = get_current_operator_name()
    try:
        batch_id = apply_adjustment_rows(
            supabase,
            department,
            category,
            adjustment_df,
            username,
            source_type="daily_outbound",
        )
    except Exception as error:
        st.error(f"{text['save_error']}: {error}")
        return

    try:
        audit, mismatches = audit_outbound_batch(
            supabase, batch_id, adjustment_df
        )
    except Exception as error:
        st.error(f"{text['audit_failed']}: {error}")
        return

    render_outbound_audit(audit, mismatches, text)
    if not audit["passed"]:
        return

    store_outbound_audit_feedback(audit)
    st.session_state["inventory_saved_message"] = (
        f"{total:,} {text['saved']}"
    )
    st.session_state["daily_outbound_version"] = version + 1
    finish_daily_outbound_backfill()
    st.rerun()


def outbound_specs_signature(outbound_specs):
    source = "|".join(
        f"{key}:{tuple(value)}"
        for key, value in sorted(outbound_specs.items())
    )
    return sha1(source.encode()).hexdigest()[:10]


def build_package_column_config(language, outbound_specs=None):
    columns = COLUMNS[language]
    colors = list(COLORS[language].values())
    config = {
        columns["包装规格"]: st.column_config.SelectboxColumn(
            columns["包装规格"],
            options=[
                translate_package(value, language)
                for value in (outbound_specs or OUTBOUND_SPECS)
            ],
            required=True,
        ),
        columns["颜色"]: st.column_config.SelectboxColumn(
            columns["颜色"], options=colors, required=True
        ),
        columns["备注"]: st.column_config.TextColumn(columns["备注"]),
    }
    for size in SIZE_COLUMNS:
        config[size] = st.column_config.NumberColumn(
            size, min_value=0, step=1, format="%d"
        )
    return config
