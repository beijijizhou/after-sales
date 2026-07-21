from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    DEFAULT_CATEGORY,
    DEFAULT_DEPARTMENT,
    INVENTORY_CATEGORIES,
    load_inventory_departments,
)
from ui.inventory.i18n import t

def render_department_selector(supabase):
    departments = load_inventory_departments(supabase)
    options = list(dict.fromkeys([DEFAULT_DEPARTMENT, *departments, "自定义"]))
    selected = st.selectbox(
        t("库存部门"), options, index=0, key="inventory_department_selector",
        format_func=t,
    )
    if selected == "自定义":
        return st.text_input(
            t("自定义部门"), value="", key="inventory_department_custom"
        ).strip()
    return selected


def render_category_selector(department):
    default_category = DEFAULT_CATEGORY if department == DEFAULT_DEPARTMENT else ""
    options = ["", *INVENTORY_CATEGORIES]
    default_index = options.index(default_category) if default_category in options else 0
    return st.selectbox(
        t("库存品类"), options, index=default_index, key="inventory_category",
        format_func=t,
    )


def render_inventory_date_selector():
    today = datetime.now(ZoneInfo("America/New_York")).date()
    return st.date_input(
        t("查看库存日期"),
        value=today,
        max_value=today,
        key="inventory_snapshot_date",
    )
