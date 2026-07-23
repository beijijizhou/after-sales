from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import DEFAULT_DEPARTMENT, SIZE_COLUMNS
from db.inventory.core.constants import UV_MODEL_ORDER
from ui.inventory.i18n import t


PREFERRED_DEPARTMENTS = ["DTF", "UV", "3D"]
PREFERRED_CATEGORIES = ["黑白短袖", "彩色短袖", "卫衣"]
PREFERRED_MATERIALS = ["160g", "180g", "CVC"]
PREFERRED_COLORS = ["黑", "白"]


def render_inventory_global_filters(dimensions, key="inventory_global"):
    dimensions = _normalize_dimensions(dimensions)
    departments = _ordered_options(
        dimensions.get("department", []), PREFERRED_DEPARTMENTS
    )
    department_col, category_col, brand_col = st.columns(3)
    material_col, color_col, size_col = st.columns(3)
    department = department_col.selectbox(
        t("库存部门"), departments, key=f"{key}_department", format_func=t
    )

    department_rows = dimensions[dimensions["department"] == department]
    preferred_categories = PREFERRED_CATEGORIES if department == "DTF" else []
    categories = _ordered_options(
        department_rows.get("category", []), preferred_categories
    )
    category_options = ["", *categories]
    category_key = f"{key}_category"
    _reset_invalid_selectbox(category_key, category_options)
    initialization_key = f"{category_key}_default_v2"
    if initialization_key not in st.session_state:
        if not st.session_state.get(category_key) and "黑白短袖" in categories:
            st.session_state[category_key] = "黑白短袖"
        st.session_state[initialization_key] = True
    category = category_col.selectbox(
        t("库存品类"), category_options, key=category_key,
        format_func=lambda value: t("全部品类") if not value else t(value),
    )

    category_rows = department_rows
    if category:
        category_rows = category_rows[category_rows["category"] == category]

    brands = _ordered_options(
        category_rows.get("brand", []), [], include_missing=False
    )
    _reset_invalid_multiselect(f"{key}_brands", brands)
    selected_brands = brand_col.multiselect(
        t("筛选品牌"), brands, key=f"{key}_brands",
        placeholder=t("全部"),
    )

    material_rows = category_rows
    if selected_brands:
        material_rows = material_rows[
            material_rows["brand"].isin(selected_brands)
        ]
    materials = _ordered_options(
        material_rows.get("material", []),
        PREFERRED_MATERIALS if department == "DTF" else [],
        include_missing=False,
    )
    _reset_invalid_multiselect(f"{key}_materials", materials)
    selected_materials = material_col.multiselect(
        t("筛选材质"), materials, key=f"{key}_materials",
        placeholder=t("全部"),
    )

    color_rows = material_rows
    if selected_materials:
        color_rows = color_rows[color_rows["material"].isin(selected_materials)]
    colors = _ordered_options(
        color_rows.get("color", []),
        PREFERRED_COLORS if department == "DTF" else [],
        include_missing=False,
    )
    _reset_invalid_multiselect(f"{key}_colors", colors)
    selected_colors = color_col.multiselect(
        t("筛选颜色"), colors, key=f"{key}_colors",
        placeholder=t("全部"),
    )

    size_rows = color_rows
    if selected_colors:
        size_rows = size_rows[size_rows["color"].isin(selected_colors)]
    sizes = _ordered_options(
        size_rows.get("size", []),
        SIZE_COLUMNS if department == "DTF" else UV_MODEL_ORDER,
        include_missing=False,
    )
    _reset_invalid_multiselect(f"{key}_sizes", sizes)
    size_filter_label = "筛选尺码" if department == "DTF" else "筛选型号"
    selected_sizes = size_col.multiselect(
        t(size_filter_label), sizes, key=f"{key}_sizes",
        placeholder=t("全部"),
        format_func=lambda value: "yuan" if value == "YUAN" else value,
    )
    movement_col, date_col = st.columns(2)
    movement_types = movement_col.multiselect(
        t("出入库类型"), ["入库", "出库"], format_func=t,
        key=f"{key}_movement_types", placeholder=t("全部"),
    )
    today = datetime.now(ZoneInfo("America/New_York")).date()
    selected_date = date_col.date_input(
        t("查看库存日期"), value=today, max_value=today,
        key=f"{key}_snapshot_date",
    )
    return (
        department, category, selected_brands, selected_materials,
        selected_colors, selected_sizes, movement_types, selected_date,
    )


def filter_inventory_rows(
    df, category="", brands=None, materials=None, colors=None, sizes=None
):
    if df.empty:
        return df
    result = df.copy()
    if category and "category" in result.columns:
        result = result[result["category"] == category]
    if brands and "brand" in result.columns:
        result = result[result["brand"].isin(brands)]
    if materials and "material" in result.columns:
        result = result[result["material"].isin(materials)]
    if colors and "color" in result.columns:
        result = result[result["color"].isin(colors)]
    if sizes and "size" in result.columns:
        result = result[result["size"].isin(sizes)]
    return result.reset_index(drop=True)


def build_inventory_filter_title(
    category="", brands=None, materials=None, colors=None, sizes=None,
):
    parts = [t(category) if category else t("全部品类")]
    for values in [brands, materials, colors, sizes]:
        if values:
            parts.append("/".join(t(str(value)) for value in values))
    return " · ".join(part for part in parts if part)


def _normalize_dimensions(dimensions):
    columns = [
        "department", "category", "brand", "material", "color", "size"
    ]
    result = pd.DataFrame(dimensions).copy()
    for column in columns:
        if column not in result.columns:
            result[column] = ""
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result[columns]


def _ordered_options(values, preferred, include_missing=True):
    available = {
        str(value).strip() for value in values
        if pd.notna(value) and str(value).strip()
    }
    ordered = list(dict.fromkeys(
        preferred if include_missing else [
            value for value in preferred if value in available
        ]
    ))
    return [*ordered, *sorted(available - set(ordered))]


def _reset_invalid_selectbox(key, options):
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def _reset_invalid_multiselect(key, options):
    if key not in st.session_state:
        return
    st.session_state[key] = [
        value for value in st.session_state[key] if value in options
    ]


def render_department_category_filters(dimensions, key="inventory_shared"):
    departments = sorted({
        str(value).strip() for value in dimensions.get("department", [])
        if pd.notna(value) and str(value).strip()
    })
    if DEFAULT_DEPARTMENT not in departments:
        departments.insert(0, DEFAULT_DEPARTMENT)
    col1, col2 = st.columns(2)
    department_label = col1.selectbox(
        "部门", ["全部部门", *departments, "自定义"], key=f"{key}_department"
    )
    if department_label == "自定义":
        department = col1.text_input(
            "自定义部门", key=f"{key}_department_custom"
        ).strip()
    else:
        department = None if department_label == "全部部门" else department_label
    category_rows = dimensions
    if department and not dimensions.empty:
        category_rows = dimensions[dimensions["department"] == department]
    categories = sorted({
        str(value).strip() for value in category_rows.get("category", [])
        if pd.notna(value) and str(value).strip()
    })
    category_label = col2.selectbox(
        "品类", ["全部品类", *categories, "自定义"], key=f"{key}_category"
    )
    if category_label == "自定义":
        category = col2.text_input(
            "自定义品类", key=f"{key}_category_custom"
        ).strip()
    else:
        category = None if category_label == "全部品类" else category_label
    return department, category
