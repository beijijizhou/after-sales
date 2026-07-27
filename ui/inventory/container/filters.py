import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.core.constants import UV_MODEL_ORDER
from ui.inventory.i18n import t
from ui.inventory.shared.filters import (
    PREFERRED_CATEGORIES,
    PREFERRED_COLORS,
    PREFERRED_DEPARTMENTS,
    PREFERRED_MATERIALS,
    _normalize_dimensions,
    _ordered_options,
    _reset_invalid_multiselect,
    _reset_invalid_selectbox,
)


def render_container_inventory_filters(
    dimensions,
    key="container_shared",
):
    dimensions = _normalize_dimensions(dimensions)
    departments = _ordered_options(
        dimensions["department"],
        PREFERRED_DEPARTMENTS,
        include_missing=False,
    )
    department_col, category_col, brand_col = st.columns(3)
    material_col, color_col, size_col = st.columns(3)
    department_options = ["", *departments]
    _reset_invalid_selectbox(f"{key}_department", department_options)
    department = department_col.selectbox(
        t("库存部门"),
        department_options,
        key=f"{key}_department",
        format_func=lambda value: (
            t("全部部门") if not value else t(value)
        ),
    )
    rows = (
        dimensions[dimensions["department"] == department]
        if department else dimensions
    )
    categories = _ordered_options(
        rows["category"],
        PREFERRED_CATEGORIES if department in {"", "DTF"} else [],
        include_missing=False,
    )
    category_options = ["", *categories]
    _reset_invalid_selectbox(f"{key}_category", category_options)
    category = category_col.selectbox(
        t("库存品类"),
        category_options,
        key=f"{key}_category",
        format_func=lambda value: (
            t("全部品类") if not value else t(value)
        ),
    )
    if category:
        rows = rows[rows["category"] == category]

    selections = []
    filter_specs = [
        ("brand", brand_col, "筛选品牌", []),
        ("material", material_col, "筛选材质", PREFERRED_MATERIALS),
        ("color", color_col, "筛选颜色", PREFERRED_COLORS),
        (
            "size",
            size_col,
            "筛选尺码" if department in {"", "DTF"} else "筛选型号",
            SIZE_COLUMNS if department in {"", "DTF"} else UV_MODEL_ORDER,
        ),
    ]
    for column, widget, label, preferred in filter_specs:
        options = _ordered_options(
            rows[column], preferred, include_missing=False
        )
        selection_key = f"{key}_{column}"
        _reset_invalid_multiselect(selection_key, options)
        selected = widget.multiselect(
            t(label),
            options,
            key=selection_key,
            placeholder=t("全部"),
        )
        selections.append(selected)
        if selected:
            rows = rows[rows[column].isin(selected)]
    return department or None, category or None, *selections
