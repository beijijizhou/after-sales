import pandas as pd
import streamlit as st

from db.consumables import reverse_consumable_batch
from ui.consumables.units import to_boxes
from utils.auth import get_current_operator_name


TYPE_LABELS = {
    "inbound": "入库",
    "issue": "领用",
    "adjustment": "库存修正",
    "reversal": "撤销",
}


def render_history(batches_df, movements_df, items_df, show_cost):
    st.subheader("耗材出入库历史")
    normal = batches_df[batches_df["movement_type"] != "reversal"].copy()
    if normal.empty:
        st.info("暂无耗材出入库记录。")
        return
    selected_id = _render_batch_selector(normal, "consumable_history_batch")
    if selected_id:
        _render_batch_detail(selected_id, movements_df, items_df, show_cost)


def render_reversals(
    supabase, batches_df, movements_df, items_df, can_edit, show_cost
):
    st.subheader("撤销耗材记录")
    reversed_ids = set(
        batches_df["reversal_of_batch_id"].dropna().astype(str)
    )
    candidates = batches_df[
        (batches_df["movement_type"] != "reversal")
        & ~batches_df["id"].astype(str).isin(reversed_ids)
    ].copy()
    if candidates.empty:
        st.info("当前没有可以撤销的耗材记录。")
    else:
        selected_id = _render_batch_selector(
            candidates, "consumable_reverse_batch"
        )
        _render_batch_detail(selected_id, movements_df, items_df, show_cost)
        if can_edit:
            confirmed = st.checkbox(
                "我确认整批撤销以上记录",
                key=f"confirm_consumable_reverse_{selected_id}",
            )
            if st.button(
                "撤销这笔耗材记录",
                width="stretch",
                disabled=not confirmed,
            ):
                try:
                    reverse_consumable_batch(
                        supabase, selected_id, get_current_operator_name()
                    )
                except Exception as error:
                    st.error(f"撤销失败：{error}")
                    return
                st.session_state["consumable_saved_message"] = (
                    "耗材记录已撤销，库存已经恢复。"
                )
                st.rerun()
        else:
            st.info("当前账号只有查看权限，不能撤销耗材记录。")

    reversals = batches_df[batches_df["movement_type"] == "reversal"]
    if not reversals.empty:
        st.divider()
        st.subheader("已撤销记录")
        selected = _render_batch_selector(
            reversals, "consumable_reversal_history"
        )
        _render_batch_detail(selected, movements_df, items_df, show_cost)


def _render_batch_selector(batch_df, key):
    labels = {}
    for row in batch_df.to_dict("records"):
        created_at = pd.to_datetime(row["created_at"], errors="coerce", utc=True)
        entered = (
            created_at.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M")
            if not pd.isna(created_at) else ""
        )
        labels[str(row["id"])] = (
            f"{entered}｜{TYPE_LABELS.get(row['movement_type'], row['movement_type'])}"
            f"｜{row['movement_date']}｜{row['created_by']}"
        )
    options = list(labels)
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
    selected = st.selectbox(
        "选择记录", options,
        format_func=lambda value: labels[value],
        key=key,
    )
    st.caption("输入时间｜类型｜出入库日期｜操作人")
    return selected


def _render_batch_detail(batch_id, movements_df, items_df, show_cost):
    detail = movements_df[
        movements_df["batch_id"].astype(str) == str(batch_id)
    ].copy()
    if detail.empty:
        st.info("这笔记录没有可显示的明细。")
        return
    item_columns = [
        "id", "category", "name", "specification", "brand", "base_unit",
        "package_unit", "units_per_package",
    ]
    detail = detail.merge(
        items_df[item_columns], left_on="item_id", right_on="id", how="left"
    )
    detail["类型"] = detail["quantity_change"].apply(
        lambda value: "增加" if float(value) > 0 else "扣减"
    )
    detail["箱数"] = detail.apply(
        lambda row: _absolute_boxes(row["quantity_change"], row), axis=1
    )
    detail["操作后库存（箱）"] = detail.apply(
        lambda row: to_boxes(row["quantity_after"], row), axis=1
    )
    display = detail.rename(columns={
        "category": "分类", "name": "耗材名称",
        "specification": "规格/型号", "brand": "品牌",
        "unit_cost": "单位成本", "note": "备注",
    })
    columns = [
        "类型", "分类", "耗材名称", "规格/型号", "品牌",
        "箱数", "操作后库存（箱）", "备注",
    ]
    if show_cost:
        columns.insert(-1, "单位成本")
    st.dataframe(
        display[columns], width="stretch", hide_index=True,
        column_config={
            "箱数": st.column_config.NumberColumn(format="%.2f"),
            "操作后库存（箱）": st.column_config.NumberColumn(format="%.2f"),
            "单位成本": st.column_config.NumberColumn(format="$%.4f"),
        },
    )


def _absolute_boxes(quantity, item):
    value = to_boxes(quantity, item)
    return None if value is None else abs(value)
