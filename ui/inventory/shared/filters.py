import pandas as pd
import streamlit as st

from db.inventory import DEFAULT_DEPARTMENT


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
