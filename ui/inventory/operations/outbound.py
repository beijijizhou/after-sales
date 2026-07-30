import streamlit as st
import pandas as pd

from db.inventory import SIZE_COLUMNS, apply_adjustment_rows, normalize_adjustment_rows
from db.inventory.operations.outbound import (
    OUTBOUND_SPECS,
    build_outbound_package_template,
    convert_packages_to_adjustments,
    normalize_outbound_packages,
)
from db.inventory.operations.outbound_audit import (
    audit_outbound_batch,
    find_outbound_inventory_issues,
    load_outbound_inventory,
)
from ui.inventory.operations.adjustment_preview import render_adjustment_preview_editor
from ui.inventory.i18n import get_language
from ui.inventory.operations.outbound_feedback import (
    render_outbound_audit,
    render_outbound_preview_summary,
    store_outbound_audit_feedback,
)
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


def render_daily_outbound(supabase, department, category):
    language = get_language()
    text = TEXT[language]
    st.subheader(text["title"])
    st.warning(text["notice"])

    version = st.session_state.get("daily_outbound_version", 0)
    template_df = to_display_table(build_outbound_package_template(), language)
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
        key=f"daily_outbound_upload_{language}_{version}",
    )
    if uploaded_file is not None:
        try:
            template_df = (
                pd.read_csv(uploaded_file)
                if uploaded_file.name.lower().endswith(".csv")
                else pd.read_excel(uploaded_file)
            )
            template_df = to_display_table(
                normalize_outbound_packages(to_internal_table(template_df, language)),
                language,
            )
        except Exception as error:
            st.error(f"{text['read_error']}: {error}")
            return

    st.caption(text["caption"])
    st.markdown(f"**{text['rules_title']}**")
    st.info(text["rules_help"])
    packaging_rules, sku_packaging_rules = render_packaging_rule_editor(
        supabase,
        department,
        category,
        language,
    )
    package_df = st.data_editor(
        template_df,
        hide_index=True,
        width="stretch",
        disabled=[COLUMNS[language]["包装规格"]],
        column_config=build_package_column_config(language),
        key=(
            f"daily_outbound_editor_{language}_{version}_"
            f"{getattr(uploaded_file, 'size', 0)}"
        ),
    )
    package_df = normalize_outbound_packages(to_internal_table(package_df, language))
    adjustment_df = convert_packages_to_adjustments(
        package_df,
        packaging_rules,
        sku_packaging_rules,
    )
    if not adjustment_df.empty:
        adjustment_df["备注"] = "仓库每日出货"
    if adjustment_df.empty:
        st.info(text["empty"])
        return

    st.markdown(f"#### {text['preview']}")
    preview_df = render_adjustment_preview_editor(
        adjustment_df,
        key=(
            f"daily_outbound_preview_{language}_{version}_"
            f"{getattr(uploaded_file, 'size', 0)}"
        ),
        lock_operation=True,
        lock_identity=True,
        allow_rows=False,
    )
    adjustment_df = normalize_adjustment_rows(preview_df)
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
    st.rerun()


def build_package_column_config(language):
    columns = COLUMNS[language]
    colors = list(COLORS[language].values())
    config = {
        columns["日期"]: st.column_config.DateColumn(columns["日期"], required=True),
        columns["包装规格"]: st.column_config.SelectboxColumn(
            columns["包装规格"],
            options=[translate_package(value, language) for value in OUTBOUND_SPECS],
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
