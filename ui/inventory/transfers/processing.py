from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.warehouses import (
    TRANSFER_STATUS_LABELS,
    build_transfer_line_editor,
    complete_pending_transfer,
    dispatch_transfer,
    normalize_transfer_execution_lines,
    receive_transfer,
    reverse_transfer,
)
from utils.auth import get_current_operator_name


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_transfer_processing(
    supabase, warehouses, balances, orders, all_lines, can_edit,
):
    st.subheader("调拨单")
    if orders.empty:
        st.info("暂无调拨任务。")
        return
    summary = build_order_summary(orders, all_lines)
    status_options = ["待处理", "全部", *TRANSFER_STATUS_LABELS.values()]
    status_filter = st.segmented_control(
        "查看状态", status_options, default="待处理",
        key="transfer_status_filter",
    )
    if status_filter == "待处理":
        visible = summary[summary["状态"].isin(["待配货", "运输中"])]
    elif status_filter == "全部":
        visible = summary
    else:
        visible = summary[summary["状态"] == status_filter]
    if visible.empty:
        st.info("当前状态没有调拨单。")
        return
    st.dataframe(
        visible.drop(columns=["调拨ID"]), hide_index=True, width="stretch",
        column_config={
            "创建时间（纽约）": st.column_config.DatetimeColumn(
                "创建时间（纽约）", format="YYYY-MM-DD HH:mm"
            ),
        },
    )
    choices = dict(zip(visible["调拨ID"], visible["调拨单号"]))
    order_id = st.selectbox(
        "选择调拨单查看完整明细", list(choices),
        format_func=choices.get, key="transfer_order_selection",
    )
    order = orders[orders["id"].astype(str) == str(order_id)].iloc[0]
    detail = all_lines[
        all_lines["transfer_order_id"].astype(str) == str(order_id)
    ]
    render_order_detail(
        supabase, warehouses, balances, order, detail, can_edit
    )


def render_order_detail(
    supabase, warehouses, balances, order, detail, can_edit,
):
    status = str(order["status"])
    st.markdown(f"#### {order['transfer_number']}｜{TRANSFER_STATUS_LABELS[status]}")
    st.caption(
        f"来源：{order.get('from_warehouse') or '现场决定'}｜"
        f"目标：{order['to_warehouse']}｜创建人：{order.get('created_by') or '—'}"
    )
    st.caption("调拨规则 warehouse-transfer-v1：只移动仓库分布，不改变公司总库存。")
    if order.get("note"):
        st.info(str(order["note"]))
    mode = "receive" if status == "in_transit" else "dispatch"
    editor = build_transfer_line_editor(detail, mode=mode)
    source = None
    if status == "pending" and can_edit:
        warehouse_codes = warehouses["code"].tolist()
        source_options = [
            code for code in warehouse_codes if code != order["to_warehouse"]
        ]
        source_default = (
            source_options.index(order["from_warehouse"])
            if order.get("from_warehouse") in source_options else 0
        )
        source = st.selectbox(
            "实际来源仓库", source_options, index=source_default,
            key=f"transfer_source_{order['id']}",
        )
        editor.insert(
            editor.columns.get_loc("实际发出"), "来源仓现有",
            editor["库存ID"].map(
                warehouse_quantity_map(balances, source)
            ).fillna(0).astype(int),
        )
    editable_columns = (
        ["本次收到", "目标库位", "备注"]
        if mode == "receive"
        else ["实际发出", "来源库位", "目标库位", "备注"]
    )
    if not can_edit or status not in {"pending", "in_transit"}:
        disabled = list(editor.columns)
    else:
        disabled = [
            column for column in editor.columns
            if column not in editable_columns
        ]
    edited = st.data_editor(
        editor, hide_index=True, width="stretch",
        key=f"transfer_detail_editor_{order['id']}_{status}",
        disabled=disabled,
        column_config={"明细ID": None, "库存ID": None},
    )
    st.download_button(
        "下载调拨单 CSV",
        data=build_transfer_export(order, edited).to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=f"{order['transfer_number']}.csv",
        mime="text/csv",
        width="stretch",
        key=f"download_transfer_{order['id']}_{status}",
    )
    if not can_edit:
        return
    if status == "pending":
        payload = normalize_transfer_execution_lines(edited)
        left, right = st.columns(2)
        if left.button("确认发出", type="primary", width="stretch"):
            dispatch_transfer(
                supabase, order["id"], source, payload,
                get_current_operator_name(),
            )
            _saved("调拨单已发出，库存进入在途。")
        if right.button("直接完成调拨", width="stretch"):
            complete_pending_transfer(
                supabase, order["id"], source, payload,
                get_current_operator_name(),
            )
            _saved("调拨已直接完成。")
    elif status == "in_transit":
        payload = normalize_transfer_execution_lines(edited, mode="receive")
        if st.button("确认实际收到", type="primary", width="stretch"):
            receive_transfer(
                supabase, order["id"], payload,
                get_current_operator_name(),
            )
            _saved("目标仓库已确认收到。")
    if status in {"pending", "in_transit", "completed"}:
        render_reversal(supabase, order, status)


def render_reversal(supabase, order, status):
    with st.expander("取消或撤销调拨", expanded=False):
        action = "取消补货任务" if status == "pending" else "撤销调拨"
        confirmed = st.checkbox(
            f"我确认{action}，原记录仍会保留",
            key=f"reverse_transfer_confirm_{order['id']}",
        )
        if st.button(
            action, disabled=not confirmed,
            key=f"reverse_transfer_{order['id']}",
        ):
            reverse_transfer(
                supabase, order["id"], get_current_operator_name()
            )
            _saved(f"{action}已完成。")


def build_order_summary(orders, lines):
    result = orders.copy()
    line_frame = pd.DataFrame(lines)
    if line_frame.empty:
        aggregates = pd.DataFrame(columns=["id", "SKU数", "已发出", "已收到"])
    else:
        aggregates = line_frame.groupby("transfer_order_id", as_index=False).agg(
            SKU数=("inventory_item_id", "nunique"),
            已发出=("quantity_sent", "sum"),
            已收到=("quantity_received", "sum"),
        ).rename(columns={"transfer_order_id": "id"})
    result = result.merge(aggregates, on="id", how="left")
    for column in ["SKU数", "已发出", "已收到"]:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    result["状态"] = result["status"].map(TRANSFER_STATUS_LABELS)
    result["来源仓"] = result["from_warehouse"].fillna("现场决定")
    result["目标仓"] = result["to_warehouse"]
    result["创建时间（纽约）"] = pd.to_datetime(
        result["created_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    return result.rename(columns={
        "id": "调拨ID", "transfer_number": "调拨单号", "note": "说明",
        "created_by": "创建人",
    })[[
        "调拨ID", "调拨单号", "状态", "来源仓", "目标仓",
        "SKU数", "已发出", "已收到", "说明", "创建人", "创建时间（纽约）",
    ]]


def warehouse_quantity_map(balances, warehouse_code):
    source = pd.DataFrame(balances)
    if source.empty:
        return {}
    source = source[source["warehouse_code"] == warehouse_code]
    return source.groupby("inventory_item_id")["quantity"].sum().to_dict()


def build_transfer_export(order, detail):
    result = detail.drop(columns=["明细ID", "库存ID"], errors="ignore").copy()
    result.insert(0, "调拨单号", order["transfer_number"])
    result.insert(1, "状态", TRANSFER_STATUS_LABELS[str(order["status"])])
    result.insert(2, "来源仓", order.get("from_warehouse") or "现场决定")
    result.insert(3, "目标仓", order["to_warehouse"])
    return result


def _saved(message):
    st.session_state["warehouse_transfer_saved"] = message
    st.rerun()
