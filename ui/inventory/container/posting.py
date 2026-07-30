import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.tables import build_container_display
from db.inventory.container.workflow import post_container_inventory
from ui.inventory.container.tables import (
    render_container_detail,
    render_container_inventory_summary,
)
from ui.inventory.container.cost_editor import (
    auto_save_container_costs,
    can_edit_container_cost,
)
from utils.auth import get_current_operator_name, has_permission


def load_pending_containers(
    supabase, department, category, brands, materials, colors, sizes,
):
    return load_inventory_containers(
        supabase,
        department=department,
        category=category,
        statuses=["已到柜"],
        brands=brands,
        materials=materials,
        colors=colors,
        sizes=sizes,
    )


def render_pending_container_posting(supabase, raw_df):
    st.subheader("待确认入库")
    st.caption(
        "货柜已经到柜，但尚未增加库存。确认后整柜一次性入库，"
        "同一货柜不能重复入库。"
    )
    if raw_df.empty:
        st.info("当前没有等待入库的货柜")
        return

    render_container_inventory_summary(
        raw_df, "待入库库存汇总"
    )
    summary = (
        raw_df.groupby(
            ["container_key", "container_no", "actual_arrival_date"],
            dropna=False,
            as_index=False,
        )["quantity"]
        .sum()
        .rename(columns={
            "container_key": "货柜记录ID",
            "container_no": "货柜号",
            "actual_arrival_date": "实际到柜日期",
            "quantity": "待入库件数",
        })
    )
    summary["实际到柜日期"] = pd.to_datetime(
        summary["实际到柜日期"], errors="coerce"
    ).dt.date
    selected = st.dataframe(
        summary.drop(columns="货柜记录ID"),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="pending_container_posting",
        column_config={
            "实际到柜日期": st.column_config.DateColumn("实际到柜日期"),
            "待入库件数": st.column_config.NumberColumn(
                "待入库件数", format="%d"
            ),
        },
    )
    if not selected.selection.rows:
        st.info("选择一个货柜查看明细并确认入库")
        return

    row = summary.iloc[selected.selection.rows[0]]
    container_key = row["货柜记录ID"]
    target = raw_df[raw_df["container_key"] == container_key]
    edited_detail_df = render_container_detail(
        build_container_display(
            target, include_cost=has_permission("can_view_cost")
        ),
        container_key,
        editable_cost=can_edit_container_cost(),
    )
    auto_save_container_costs(
        supabase, raw_df, container_key, edited_detail_df
    )
    if not has_permission("can_edit_container"):
        st.info("当前账号可以查看，但不能确认入库")
        return

    note = st.text_input(
        "入库备注",
        key=f"container_posting_note_{container_key}",
    )
    total = int(pd.to_numeric(target["quantity"]).sum())
    st.warning(f"确认后库存将增加 {total:,} 件")
    if not st.button(
        "确认入库",
        type="primary",
        width="stretch",
        key=f"post_container_{container_key}",
    ):
        return
    try:
        post_container_inventory(
            supabase,
            container_key,
            get_current_operator_name(),
            note,
        )
        st.success(f"入库成功：库存增加 {total:,} 件")
        st.toast("货柜已完成入库")
        st.rerun()
    except Exception as error:
        st.error(f"确认入库失败：{error}")
