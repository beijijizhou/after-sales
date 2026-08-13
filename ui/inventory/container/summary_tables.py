"""Container inventory summary views."""

import pandas as pd
import streamlit as st

from db.inventory.container.tables import build_container_display, build_container_inventory_summary, build_filtered_container_summary
from ui.table_layout import fit_table_height


def render_container_inventory_summary(raw, title):
    if raw.empty:
        return
    st.subheader(title)
    st.caption("已合并当前筛选范围内的货柜、品牌和材质；可用页面顶部筛选器缩小范围。")
    departments = raw.get("department", pd.Series("", index=raw.index)).fillna("").astype(str).str.strip()
    names = departments.drop_duplicates().tolist()
    for department in names:
        if len(names) > 1:
            st.markdown(f"**{department or '未分类部门'}**")
        _render_summary(raw[departments == department])


def render_filtered_container_summary(raw):
    summary = build_filtered_container_summary(raw)
    if summary.empty:
        return
    st.subheader("筛选结果汇总")
    st.caption("以下数量严格按照页面当前的部门、品类、品牌、材质、颜色和尺码筛选汇总。")
    fixed = {"涉及货柜", "部门", "品类", "品牌", "材质", "颜色", "总件数"}
    items = [column for column in summary.columns if column not in fixed]
    st.dataframe(summary, hide_index=True, width="stretch", height=fit_table_height(summary), column_config={
        "涉及货柜": st.column_config.TextColumn("涉及货柜", width="medium"),
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        **{item: st.column_config.NumberColumn(_item_label(item), format="%d") for item in items},
    })


def _render_summary(raw):
    summary = build_container_inventory_summary(build_container_display(raw, include_cost=False))
    if summary.empty:
        return
    items = [column for column in summary.columns if column not in {"材质", "颜色", "总件数"}]
    st.dataframe(summary, hide_index=True, width="stretch", height=fit_table_height(summary), column_config={
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        **{item: st.column_config.NumberColumn(_item_label(item), format="%d") for item in items},
    })


def _item_label(value):
    return "yuan" if str(value).upper() == "YUAN" else value
