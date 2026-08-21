import pandas as pd
import streamlit as st

from db.batches import (
    BatchKind,
    BatchReference,
    filter_active_batch_records,
    reversed_record_ids,
)
from ui.batches import (
    render_batch_reversal_action,
    synchronize_batch_selector_state,
)
from ui.consumables.units import entry_unit, to_entry_quantity


TYPE_LABELS = {
    "inbound": "入库",
    "issue": "每日耗材出库（人工）",
    "adjustment": "库存修正",
    "reversal": "撤销",
}


def render_history(batches_df, movements_df, items_df, show_cost):
    st.subheader("耗材库存流水")
    normal = batches_df[batches_df["movement_type"] != "reversal"].copy()
    if normal.empty:
        st.info("暂无耗材出入库记录。")
        return
    statuses = _batch_status_by_id(batches_df)
    selected_id = _render_batch_selector(
        normal, "consumable_history_batch", statuses=statuses
    )
    if selected_id:
        if statuses.get(str(selected_id)) == "已撤销":
            reversal = batches_df[
                batches_df["reversal_of_batch_id"].astype(str)
                == str(selected_id)
            ]
            restored_at = ""
            if not reversal.empty:
                created_at = pd.to_datetime(
                    reversal.iloc[0].get("created_at"), errors="coerce", utc=True
                )
                if not pd.isna(created_at):
                    restored_at = created_at.tz_convert(
                        "America/New_York"
                    ).strftime("%Y-%m-%d %H:%M")
            suffix = f"（纽约时间 {restored_at}）" if restored_at else ""
            st.success(
                "这笔批次已经撤销，库存已恢复"
                f"{suffix}；下方保留的是原始历史快照。"
            )
        _render_batch_detail(selected_id, movements_df, items_df, show_cost)


def render_reversals(
    supabase, batches_df, movements_df, items_df, can_edit, show_cost
):
    st.subheader("撤销耗材记录")
    st.caption(
        "统一撤销规则：整批生成反向流水，原记录、撤销记录、操作人和"
        "时间全部保留；不直接删除或覆盖历史。"
    )
    candidates = filter_active_batch_records(
        batches_df, type_column="movement_type"
    )
    if candidates.empty:
        st.info("当前没有可以撤销的耗材记录。")
    else:
        selected_id = _render_batch_selector(
            candidates, "consumable_reverse_batch"
        )
        _render_batch_detail(selected_id, movements_df, items_df, show_cost)
        if can_edit:
            render_batch_reversal_action(
                supabase,
                BatchReference(BatchKind.CONSUMABLE, selected_id),
                key_scope="consumable",
                confirmation_label="我确认整批撤销以上记录",
                button_label="撤销这笔耗材记录",
                success_state_key="consumable_saved_message",
                success_message="耗材记录已撤销，库存已经恢复。",
            )
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


def _render_batch_selector(batch_df, key, statuses=None):
    statuses = statuses or {}
    labels = {}
    for row in batch_df.to_dict("records"):
        created_at = pd.to_datetime(row["created_at"], errors="coerce", utc=True)
        entered = (
            created_at.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M")
            if not pd.isna(created_at) else ""
        )
        type_label = (
            "耗材扣减核对（无库存变动）"
            if row.get("source_file_name") == "completion_ack"
            else TYPE_LABELS.get(row["movement_type"], row["movement_type"])
        )
        batch_id = str(row["id"])
        status = statuses.get(batch_id)
        status_prefix = f"【{status}】" if status else ""
        labels[batch_id] = (
            f"{status_prefix}{entered}｜{type_label}"
            f"｜{row['movement_date']}｜{row['created_by']}"
        )
    options = list(labels)
    synchronize_batch_selector_state(st.session_state, key, options)
    selected = st.selectbox(
        "选择记录", options,
        format_func=lambda value: labels[value],
        key=key,
    )
    st.caption("输入时间｜类型｜出入库日期｜操作人")
    return selected


def _batch_status_by_id(batches_df):
    reversed_ids = reversed_record_ids(batches_df)
    return {
        str(batch_id): "已撤销" if str(batch_id) in reversed_ids else "有效"
        for batch_id in batches_df.loc[
            batches_df["movement_type"] != "reversal", "id"
        ]
    }


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
    detail["数量"] = detail.apply(
        lambda row: abs(to_entry_quantity(row["quantity_change"], row)), axis=1
    )
    detail["单位"] = detail.apply(entry_unit, axis=1)
    detail["操作后库存"] = detail.apply(
        lambda row: to_entry_quantity(row["quantity_after"], row), axis=1
    )
    display = detail.rename(columns={
        "category": "分类", "name": "耗材名称",
        "specification": "规格/型号", "brand": "品牌",
        "unit_cost": "单位成本", "note": "备注",
    })
    columns = [
        "类型", "分类", "耗材名称", "规格/型号", "品牌",
        "数量", "单位", "操作后库存", "备注",
    ]
    if show_cost:
        columns.insert(-1, "单位成本")
    st.dataframe(
        display[columns], width="stretch", hide_index=True,
        column_config={
            "数量": st.column_config.NumberColumn(format="%.2f"),
            "操作后库存": st.column_config.NumberColumn(format="%.2f"),
            "单位成本": st.column_config.NumberColumn(format="$%.4f"),
        },
    )
