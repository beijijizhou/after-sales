"""Interactive SKU/package entry for daily outbound batches."""

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.operations.outbound import convert_sku_package_entries
from utils.sku_sorting import sort_sku_rows
from utils.option_values import ordered_values

SKU_ENTRY_TEXT = {
    "zh": {"title": "按 SKU 和箱规录入", "help": "只添加实际出库的 SKU；填写箱数或包数后，下方直接显示换算总件数。", "brand": "品牌", "material": "材质", "color": "颜色", "size": "尺码", "package": "包装单位", "units": "箱规（件数）", "units_help": "可留空使用换算规则；同一 SKU 有 70/72 件箱规时请直接填写。", "count": "箱数 / 包数", "total": "总件数", "total_help": "根据箱规和箱数 / 包数自动计算，不可手动修改。", "packages": {"Box": "箱", "Bag": "包"}, "import_title": "批量文件导入（可选）"},
    "en": {"title": "Enter by SKU and pack size", "help": "Add only outbound SKUs. The converted piece total appears below.", "brand": "Brand", "material": "Material", "color": "Color", "size": "Size", "package": "Package", "units": "Pieces per package", "units_help": "Leave blank for the conversion rule, or enter an exact pack size.", "count": "Boxes / bags", "total": "Total pieces", "total_help": "Calculated automatically from pack size and package count.", "packages": {"Box": "Box", "Bag": "Bag"}, "import_title": "Batch file import (optional)"},
    "es": {"title": "Registrar por SKU y empaque", "help": "Agregue solo los SKU enviados; el total convertido aparece abajo.", "brand": "Marca", "material": "Material", "color": "Color", "size": "Talla", "package": "Empaque", "units": "Piezas por empaque", "units_help": "Déjelo vacío para usar la regla o indique el empaque exacto.", "count": "Cajas / bolsas", "total": "Piezas totales", "total_help": "Se calcula automáticamente según el empaque y la cantidad.", "packages": {"Box": "Caja", "Bag": "Bolsa"}, "import_title": "Importación por archivo (opcional)"},
}


def render_sku_outbound_entry(
    sku_lookup, movement_date, packaging_rules, sku_packaging_rules,
    text, language, version, specs_signature,
):
    values = list(sku_lookup.values())
    brands = sorted({value["brand"] for value in values})
    materials = sorted({value["material"] for value in values})
    colors = ordered_values((value["color"] for value in values), ["黑", "白"])
    sizes = ordered_values((value["size"] for value in values), SIZE_COLUMNS)
    st.markdown(f"**{text['title']}**")
    st.caption(text["help"])
    labels = text["packages"]
    state_key = f"daily_outbound_sku_source_{language}_{version}_{movement_date.isoformat()}"
    table_key = f"{state_key}_table_version"
    source = pd.DataFrame(st.session_state.get(state_key, [{
        text["brand"]: None, text["material"]: None, text["color"]: None,
        text["size"]: None, text["package"]: labels["Box"],
        text["units"]: None, text["count"]: 0, text["total"]: 0,
    }]))
    display = st.data_editor(
        source, hide_index=True, width="stretch", num_rows="dynamic",
        disabled=[text["total"]],
        column_config=_column_config(text, brands, materials, colors, sizes),
        key=(f"daily_outbound_sku_editor_{language}_{version}_"
             f"{movement_date.isoformat()}_{len(sku_lookup)}_{specs_signature}_"
             f"{st.session_state.get(table_key, 0)}"),
    )
    entries = display.rename(columns={
        text["brand"]: "品牌", text["material"]: "材质",
        text["color"]: "颜色", text["size"]: "尺码",
        text["package"]: "包装单位", text["units"]: "箱规",
        text["count"]: "包装数量", text["total"]: "换算件数",
    })
    entries["包装单位"] = entries["包装单位"].map(
        {label: kind for kind, label in labels.items()}
    ).fillna("Box")
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


def _column_config(text, brands, materials, colors, sizes):
    select, number = st.column_config.SelectboxColumn, st.column_config.NumberColumn
    return {
        text["brand"]: select(text["brand"], options=brands, required=True),
        text["material"]: select(text["material"], options=materials, required=True),
        text["color"]: select(text["color"], options=colors, required=True),
        text["size"]: select(text["size"], options=sizes, required=True),
        text["package"]: select(text["package"], options=list(text["packages"].values()), required=True),
        text["units"]: number(text["units"], min_value=1, step=1, format="%d", help=text["units_help"]),
        text["count"]: number(text["count"], min_value=0, step=1, format="%d", required=True),
        text["total"]: number(text["total"], min_value=0, format="%d", help=text["total_help"]),
    }


def _row_total(row, lookup, movement_date, rules, sku_rules):
    _, preview = convert_sku_package_entries(
        pd.DataFrame([row]), lookup, movement_date, rules, sku_rules
    )
    return int(preview.iloc[0]["总件数"]) if not preview.empty else 0

