import streamlit as st
from ui.inventory.i18n import t


def render_inventory_unit_calculator():
    st.markdown(f"#### {t('临时箱数换算')}")
    box_col, unit_col, loose_col, total_col = st.columns(4)
    box_count = box_col.number_input(
        t("箱数"),
        min_value=0,
        value=0,
        step=1,
        key="inventory_calculator_box_count",
    )
    units_per_box = unit_col.number_input(
        t("每箱件数"),
        min_value=1,
        value=72,
        step=1,
        key="inventory_calculator_units_per_box",
    )
    loose_units = loose_col.number_input(
        t("零散件数"),
        min_value=0,
        value=0,
        step=1,
        key="inventory_calculator_loose_units",
    )
    total_units = int(box_count * units_per_box + loose_units)
    total_col.metric(t("换算总件数"), f"{total_units:,}")
    st.caption(t("换算结果仅供填写库存调整表，不会自动修改库存。"))
