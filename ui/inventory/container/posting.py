import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_inventory_container,
    load_inventory_containers,
)
from db.inventory.container.labels import get_container_business_name
from db.inventory.container.tables import build_container_display
from db.inventory.container.workflow import post_container_inventory
from db.inventory.core.queries import load_inventory_items
from ui.inventory.container.tables import (
    render_container_detail,
    render_container_inventory_summary,
)
from ui.inventory.container.cost_editor import (
    auto_save_container_costs,
    can_edit_container_cost,
)
from ui.inventory.container.selection import (
    container_selection_widget_key,
    selected_container_key,
)
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from utils.auth import get_current_operator_name, has_permission
from ui.table_layout import fit_table_height


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
    source = raw_df.copy()
    source["货柜备注"] = source.groupby("container_key")["note"].transform(
        lambda notes: get_container_business_name(
            source.loc[notes.index, "container_key"].iloc[0],
            source.loc[notes.index, "container_no"].iloc[0],
            notes.tolist(),
        )
    )
    summary = (
        source.groupby(
            ["container_key", "货柜备注", "container_no", "actual_arrival_date"],
            dropna=False,
            as_index=False,
        )["quantity"]
        .sum()
        .rename(columns={
            "container_key": "货柜记录ID",
            "货柜备注": "货柜备注",
            "container_no": "货柜号",
            "actual_arrival_date": "实际到柜日期",
            "quantity": "待入库件数",
        })
    )
    summary["实际到柜日期"] = pd.to_datetime(
        summary["实际到柜日期"], errors="coerce"
    ).dt.date
    container_keys = summary["货柜记录ID"].tolist()
    widget_key = container_selection_widget_key(
        st.session_state,
        "pending_container_posting",
        container_keys,
    )
    selected = st.dataframe(
        summary.drop(columns="货柜记录ID"),
        hide_index=True,
        width="stretch",
        height=fit_table_height(summary),
        on_select="rerun",
        selection_mode="single-row",
        key=widget_key,
        column_config={
            "实际到柜日期": st.column_config.DateColumn("实际到柜日期"),
            "待入库件数": st.column_config.NumberColumn(
                "待入库件数", format="%d"
            ),
        },
    )
    container_key = selected_container_key(
        container_keys, selected.selection.rows
    )
    if not container_key:
        st.info("选择一个货柜查看明细并确认入库")
        return

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
    render_container_posting_action(
        supabase, target, container_key, key_prefix="pending_container"
    )


def render_container_posting_action(
    supabase, target, container_key, key_prefix="container_posting",
):
    if target.empty:
        return
    if not has_permission("can_edit_container"):
        st.info("当前账号可以查看，但不能确认入库")
        return
    try:
        complete_target = load_inventory_container(
            supabase, container_key
        )
    except Exception as error:
        st.error(f"完整货柜明细加载失败：{error}")
        return
    if complete_target.empty:
        st.error("没有找到这个货柜的完整明细，不能确认入库")
        return
    target = complete_target

    note = st.text_input(
        "入库备注",
        key=f"{key_prefix}_note_{container_key}",
    )
    total = int(
        pd.to_numeric(target["quantity"], errors="coerce").fillna(0).sum()
    )
    add_inventory, mode_confirmed = render_container_posting_mode(
        container_key, key_prefix
    )
    if add_inventory:
        render_container_posting_stock_review(supabase, target)
        st.warning(f"确认后库存将增加 {total:,} 件")
    if not st.button(
        "确认入库" if add_inventory else "仅确认入库（不增加库存）",
        type="primary",
        width="stretch",
        disabled=not mode_confirmed,
        key=f"{key_prefix}_post_{container_key}",
    ):
        return
    post_container_with_feedback(
        supabase, container_key, note, total, add_inventory=add_inventory
    )


def render_container_posting_mode(container_key, key_prefix):
    mode = st.radio(
        "入库处理方式",
        ["正常入库（增加库存）", "库存已提前录入（仅确认入库）"],
        horizontal=True,
        key=f"{key_prefix}_posting_mode_{container_key}",
    )
    add_inventory = mode == "正常入库（增加库存）"
    if add_inventory:
        return True, True
    st.warning(
        "本次只把货柜状态改为“已入库”，不会增加库存，也不会生成库存入库流水。"
    )
    confirmed = st.checkbox(
        "我确认这个批次的库存已经通过其他入库流水计入",
        key=f"{key_prefix}_status_only_confirm_{container_key}",
    )
    return False, confirmed


def post_container_with_feedback(
    supabase, container_key, note, total, *, add_inventory=True,
):
    try:
        post_container_inventory(
            supabase, container_key, get_current_operator_name(), note,
            add_inventory=add_inventory,
        )
        if add_inventory:
            st.success(f"入库成功：库存增加 {total:,} 件")
        else:
            st.success("入库状态已确认：库存未重复增加")
        st.toast("货柜已完成入库")
        st.rerun()
    except Exception as error:
        st.error(f"确认入库失败：{error}")


def render_container_posting_stock_review(supabase, target):
    render_container_inventory_change_review(
        supabase, target, "增加", "货柜入库库存核对"
    )


def render_container_inventory_change_review(
    supabase, target, action, title,
):
    inventory_frames = []
    scopes = target[["department", "category"]].drop_duplicates()
    try:
        for scope in scopes.to_dict("records"):
            frame = load_inventory_items(
                supabase, scope["department"], scope["category"]
            ).copy()
            frame["department"] = scope["department"]
            frame["category"] = scope["category"]
            inventory_frames.append(frame)
    except Exception as error:
        st.error(f"入库前库存核对失败：{error}")
        return
    inventory = pd.concat(inventory_frames, ignore_index=True)
    changes = target.copy()
    if action is not None:
        changes["操作"] = action
    render_inventory_change_comparison(
        build_inventory_change_comparison(inventory, changes),
        action=action, title=title,
    )
