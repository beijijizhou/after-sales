"""Container detail, totals, and packaging review views."""

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.container.labels import get_container_display_label
from db.inventory.container.packaging import build_container_packaging_summary
from db.inventory.container.tables import get_container_item_columns
from ui.table_layout import fit_table_height


def render_container_detail(display_df, container_key, editable_cost=False, show_items=True):
    detail = display_df[display_df["货柜记录ID"] == container_key].copy()
    if detail.empty:
        return
    label = get_container_display_label(
        container_key, detail["货柜号"].iloc[0],
        detail.get("备注", pd.Series(dtype=str)).tolist(),
    )
    st.subheader(f"{label} 明细")
    quantity, cost = calculate_container_totals(detail)
    if cost is None:
        st.metric("总数量", f"{quantity:,} 件")
    else:
        quantity_col, cost_col = st.columns(2)
        quantity_col.metric("总数量", f"{quantity:,} 件")
        cost_col.metric("总成本", f"${cost:,.2f}")
    edited = _render_item_detail(detail, display_df, container_key, editable_cost) if show_items else detail
    render_packaging_check(build_container_packaging_summary(display_df, container_key))
    return edited


def _render_item_detail(detail, display_df, container_key, editable_cost):
    hidden = ["货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期", "实际到货日期", "实际到货时间（纽约）", "货柜号", "状态", "确认到柜时间（纽约）"]
    detail = detail.drop(columns=hidden)
    items = get_container_item_columns(display_df)
    front = ["部门", "品类", "品牌", "材质", "颜色", "备注"]
    costs = ["成本"] if "成本" in detail.columns else []
    detail = (
        detail[[*front[:-1], *costs, "型号", "数量", "备注"]]
        if "型号" in detail.columns else detail[[*front, *costs, *items, "总件数"]]
    )
    config = _detail_config(detail, items, editable_cost)
    if editable_cost and "成本" in detail.columns:
        return st.data_editor(
            detail, hide_index=True, width="stretch", height=fit_table_height(detail),
            column_config=config, disabled=[c for c in detail.columns if c != "成本"],
            key=f"container_detail_cost_editor_{container_key}",
        )
    st.dataframe(detail, hide_index=True, width="stretch", column_config=config, height=fit_table_height(detail))
    return detail


def _detail_config(detail, items, editable_cost):
    config = {
        "备注": st.column_config.TextColumn("备注", width="large"),
        "型号": st.column_config.TextColumn("型号"),
        "数量": st.column_config.NumberColumn("数量", format="%d"),
        **{item: st.column_config.NumberColumn(_item_label(item), format="%d") for item in items},
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in detail.columns:
        config["成本"] = st.column_config.NumberColumn(
            "成本", min_value=0.0, step=0.0001, format="%.4f", disabled=not editable_cost
        )
    return config


def calculate_container_totals(detail):
    if detail.empty:
        return 0, None
    quantities = pd.to_numeric(detail["总件数"], errors="coerce").fillna(0)
    if "成本" not in detail.columns:
        return int(quantities.sum()), None
    costs = pd.to_numeric(detail["成本"], errors="coerce").fillna(0)
    return int(quantities.sum()), float((quantities * costs).sum())


def render_packaging_check(packaging, title="箱装核对"):
    if packaging.empty:
        return
    st.subheader(title)
    if any(str(value) == "混装" for size in SIZE_COLUMNS for value in packaging[size]):
        records = [value for value in packaging["包装记录"].dropna().unique() if str(value).strip()]
        st.warning(
            "默认箱规无法整除，已优先读取备注中的包装记录：" + "；".join(records)
            if records else "该货柜无法完全以箱数显示，备注中也没有包装记录。"
        )
    st.dataframe(packaging, hide_index=True, width="stretch", height=fit_table_height(packaging), column_config={
        "核对规格": st.column_config.TextColumn("核对规格", width="small"),
        "包装记录": st.column_config.TextColumn("包装记录", width="medium"),
        **{size: st.column_config.TextColumn(size, width="medium") for size in SIZE_COLUMNS},
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        "备注": st.column_config.TextColumn("备注", width="large"),
    })


def _item_label(value):
    return "yuan" if str(value).upper() == "YUAN" else value
