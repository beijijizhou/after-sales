"""Interactive SKU/package entry for daily outbound batches."""

from hashlib import sha1

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.operations.outbound import convert_sku_package_entries
from utils.sku_sorting import sort_sku_rows
from utils.option_values import ordered_values
from ui.inventory.shared.filter_models import reset_invalid_multiselect

SKU_ENTRY_TEXT = {
    "zh": {"title": "按 SKU 和包装单位录入", "help": "只添加实际出库的 SKU；默认按件录入，选择箱或包时再按包装规格换算。", "sku": "UV SKU", "material_filter": "先筛选材质", "material_filter_help": "下方只显示所选材质的 UV SKU；切换筛选会重置尚未保存的录入表。", "brand": "品牌", "material": "材质", "color": "颜色", "size": "尺码", "package": "包装单位", "units": "每箱 / 包件数", "units_help": "按件录入时无需填写；箱或包可留空使用换算规则，同一 SKU 有 70/72 件箱规时请直接填写。", "count": "数量", "total": "总件数", "total_help": "按件录入时等于数量；按箱或包录入时自动换算。", "packages": {"Piece": "件", "Box": "箱", "Bag": "包"}, "import_title": "批量文件导入（可选）"},
    "en": {"title": "Enter by SKU and package unit", "help": "Add only outbound SKUs. Piece is the default; boxes and bags use their package conversion.", "sku": "UV SKU", "brand": "Brand", "material": "Material", "color": "Color", "size": "Size", "package": "Package unit", "units": "Pieces per box / bag", "units_help": "Not needed for pieces. Leave blank to use the box or bag conversion rule.", "count": "Quantity", "total": "Total pieces", "total_help": "Equal to quantity for pieces; converted automatically for boxes or bags.", "packages": {"Piece": "Piece", "Box": "Box", "Bag": "Bag"}, "import_title": "Batch file import (optional)"},
    "es": {"title": "Registrar por SKU y unidad de empaque", "help": "Agregue solo los SKU enviados. La pieza es la unidad predeterminada.", "sku": "SKU UV", "brand": "Marca", "material": "Material", "color": "Color", "size": "Talla", "package": "Unidad", "units": "Piezas por caja / bolsa", "units_help": "No se requiere para piezas; déjelo vacío para usar la regla de conversión.", "count": "Cantidad", "total": "Piezas totales", "total_help": "Para piezas equivale a la cantidad; cajas y bolsas se convierten automáticamente.", "packages": {"Piece": "Pieza", "Box": "Caja", "Bag": "Bolsa"}, "import_title": "Importación por archivo (opcional)"},
}


def render_sku_outbound_entry(
    sku_lookup, movement_date, packaging_rules, sku_packaging_rules,
    text, language, version, specs_signature, scope="", compact_sku=False,
):
    values = list(sku_lookup.values())
    brands = sorted({value["brand"] for value in values})
    materials = sorted({value["material"] for value in values})
    colors = ordered_values((value["color"] for value in values), ["黑", "白"])
    sizes = ordered_values((value["size"] for value in values), SIZE_COLUMNS)
    st.markdown(f"**{text['title']}**")
    st.caption(text["help"])
    if compact_sku:
        base_scope_token = sha1(str(scope).encode()).hexdigest()[:10]
        filter_key = f"daily_outbound_uv_materials_{base_scope_token}"
        reset_invalid_multiselect(st.session_state, filter_key, materials)
        selected_materials = st.multiselect(
            text.get("material_filter", text["material"]), materials,
            default=materials[:1], key=filter_key,
        )
        st.caption(text.get("material_filter_help", ""))
        sku_lookup = filter_sku_lookup_by_material(
            sku_lookup, selected_materials
        )
        if not selected_materials:
            st.info(text.get("material_filter", text["material"]))
            return pd.DataFrame(), pd.DataFrame()
        scope = f"{scope}|materials:{'|'.join(selected_materials)}"
    labels = text["packages"]
    scope_token, state_key = daily_outbound_entry_state_key(
        scope, language, version, movement_date
    )
    table_key = f"{state_key}_table_version"
    identity = (
        {text["sku"]: None}
        if compact_sku else {
            text["brand"]: None, text["material"]: None,
            text["color"]: None, text["size"]: None,
        }
    )
    source = pd.DataFrame(st.session_state.get(state_key, [{
        **identity, text["package"]: labels["Piece"],
        text["units"]: None, text["count"]: 0, text["total"]: 0,
    }]))
    display = st.data_editor(
        source, hide_index=True, width="stretch", num_rows="dynamic",
        disabled=[text["total"]],
        column_config=_column_config(
            text, brands, materials, colors, sizes,
            sku_labels=list(sku_lookup) if compact_sku else None,
        ),
        key=(f"daily_outbound_sku_editor_{scope_token}_{language}_{version}_"
             f"{movement_date.isoformat()}_{len(sku_lookup)}_{specs_signature}_"
             f"{st.session_state.get(table_key, 0)}"),
    )
    entries = display.rename(columns={
        text.get("sku", "UV SKU"): "SKU",
        text["brand"]: "品牌", text["material"]: "材质",
        text["color"]: "颜色", text["size"]: "尺码",
        text["package"]: "包装单位", text["units"]: "箱规",
        text["count"]: "包装数量", text["total"]: "换算件数",
    })
    entries["包装单位"] = entries["包装单位"].map(
        {label: kind for kind, label in labels.items()}
    ).fillna("Piece")
    adjustments, preview = convert_sku_package_entries(
        entries, sku_lookup, movement_date, packaging_rules, sku_packaging_rules
    )
    totals = [
        _row_total(row, sku_lookup, movement_date, packaging_rules, sku_packaging_rules)
        for _, row in entries.iterrows()
    ]
    displayed = pd.to_numeric(
        entries["换算件数"], errors="coerce"
    ).fillna(0).astype(int).tolist()
    if displayed != totals:
        refreshed = display.copy()
        refreshed[text["total"]] = totals
        st.session_state[state_key] = refreshed.to_dict("records")
        st.session_state[table_key] = int(st.session_state.get(table_key, 0)) + 1
        st.rerun()
    return adjustments, sort_sku_rows(
        preview, material="材质", color="颜色", size="尺码", leading=["品牌"]
    )


def filter_sku_lookup_by_material(sku_lookup, selected_materials):
    selected = {
        str(value).strip() for value in selected_materials
        if str(value).strip()
    }
    if not selected:
        return {}
    return {
        label: sku for label, sku in sku_lookup.items()
        if str(sku.get("material") or "").strip() in selected
    }


def daily_outbound_entry_state_key(scope, language, version, movement_date):
    """Keep an editor's rows inside its department/category scope."""
    scope_token = sha1(str(scope).encode()).hexdigest()[:10]
    return scope_token, (
        f"daily_outbound_sku_source_{scope_token}_{language}_{version}_"
        f"{movement_date.isoformat()}"
    )


def _column_config(
    text, brands, materials, colors, sizes, sku_labels=None,
):
    select, number = st.column_config.SelectboxColumn, st.column_config.NumberColumn
    quantity_config = {
        text["package"]: select(text["package"], options=list(text["packages"].values()), required=True),
        text["units"]: number(text["units"], min_value=1, step=1, format="%d", help=text["units_help"]),
        text["count"]: number(text["count"], min_value=0, step=1, format="%d", required=True),
        text["total"]: number(text["total"], min_value=0, format="%d", help=text["total_help"]),
    }
    if sku_labels is not None:
        return {
            text["sku"]: select(
                text["sku"], options=sku_labels, required=True,
            ),
            **quantity_config,
        }
    return {
        text["brand"]: select(text["brand"], options=brands, required=True),
        text["material"]: select(text["material"], options=materials, required=True),
        text["color"]: select(text["color"], options=colors, required=True),
        text["size"]: select(text["size"], options=sizes, required=True),
        **quantity_config,
    }


def _row_total(row, lookup, movement_date, rules, sku_rules):
    _, preview = convert_sku_package_entries(
        pd.DataFrame([row]), lookup, movement_date, rules, sku_rules
    )
    return int(preview.iloc[0]["总件数"]) if not preview.empty else 0
