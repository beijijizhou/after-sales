from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.batches import BatchKind, BatchReference
from db.inventory.warehouses import (
    TRANSFER_STATUS_LABELS,
    build_transfer_line_editor,
    complete_pending_transfer,
    dispatch_transfer,
    normalize_transfer_execution_lines,
    receive_transfer,
    record_transfer_baseline,
)
from ui.inventory.transfers.request import (
    attach_warehouse_quantities,
    render_linked_inventory_item_selector,
)
from ui.batches import render_batch_reversal_action
from utils.auth import get_current_operator_name


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_transfer_processing(
    supabase, warehouses, items, balances, orders, all_lines, can_edit,
):
    st.subheader("调拨单")
    if can_edit:
        render_baseline_transfer_form(supabase, warehouses, items, balances)
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
    if not bool(order.get("balance_effect_applied", True)):
        st.info(
            order.get("balance_effect_note")
            or "期初调拨记录：只补齐调拨审计，不重复调整库存。"
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
        render_batch_reversal_action(
            supabase,
            BatchReference(BatchKind.WAREHOUSE_TRANSFER, order["id"]),
            key_scope="warehouse_transfer",
            confirmation_label=f"我确认{action}，原记录仍会保留",
            button_label=action,
            success_state_key="warehouse_transfer_saved",
            success_message=f"{action}已完成。",
        )


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
    business_dates = result.get(
        "business_date", pd.Series(pd.NaT, index=result.index)
    )
    result["业务日期"] = pd.to_datetime(
        business_dates, errors="coerce"
    ).dt.date
    result["库存处理"] = result.get(
        "balance_effect_applied", pd.Series(True, index=result.index)
    ).map({True: "已调整仓库分布", False: "期初记录（不重复调整）"})
    result["来源仓"] = result["from_warehouse"].fillna("现场决定")
    result["目标仓"] = result["to_warehouse"]
    result["创建时间（纽约）"] = pd.to_datetime(
        result["created_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    return result.rename(columns={
        "id": "调拨ID", "transfer_number": "调拨单号", "note": "说明",
        "created_by": "创建人",
    })[[
        "调拨ID", "调拨单号", "业务日期", "状态", "来源仓", "目标仓",
        "SKU数", "已发出", "已收到", "说明", "创建人", "创建时间（纽约）",
        "库存处理",
    ]]


def render_baseline_transfer_form(supabase, warehouses, items, balances):
    with st.expander("补录期初已完成调拨", expanded=False):
        st.caption(
            "仅用于仓库分布流程刚启用时：保留真实调拨单，但当前分布已包含结果，"
            "因此不会再次增减任何仓库或公司库存。"
        )
        codes = warehouses["code"].tolist()
        left, middle, right = st.columns(3)
        business_date = left.date_input(
            "调拨日期", key="baseline_transfer_business_date"
        )
        source = middle.selectbox(
            "来源仓库", codes, index=codes.index("60") if "60" in codes else 0,
            key="baseline_transfer_source",
        )
        target = right.selectbox(
            "目标仓库", codes, index=codes.index("25") if "25" in codes else 0,
            key="baseline_transfer_target",
        )
        selected_item = render_linked_inventory_item_selector(
            items, "baseline_transfer_item"
        )
        selected_key = "baseline_transfer_selected_ids"
        st.session_state.setdefault(selected_key, [])
        if st.button("加入调拨明细", key="baseline_transfer_add", width="stretch"):
            if selected_item and selected_item not in st.session_state[selected_key]:
                st.session_state[selected_key].append(selected_item)
                st.rerun()
        selected_ids = st.session_state[selected_key]
        if not selected_ids:
            st.info("加入 SKU 后填写实际调拨件数。")
            return
        selected = attach_warehouse_quantities(
            items[items["id"].isin(selected_ids)].copy(), balances
        ).rename(columns={
            "department": "部门", "category": "品类", "material": "材质",
            "brand": "品牌", "color": "颜色", "size": "尺码",
        })
        selected["本次调拨"] = 0
        selected["移除"] = False
        editor = st.data_editor(
            selected[[
                "id", "部门", "品类", "材质", "品牌", "颜色", "尺码",
                "25仓", "60仓", "70仓", "本次调拨", "移除",
            ]],
            hide_index=True, width="stretch", key="baseline_transfer_editor",
            disabled=[
                "id", "部门", "品类", "材质", "品牌", "颜色", "尺码",
                "25仓", "60仓", "70仓",
            ],
            column_config={
                "id": None,
                "本次调拨": st.column_config.NumberColumn(
                    "本次调拨", min_value=0, step=1, format="%d"
                ),
                "移除": st.column_config.CheckboxColumn("移除"),
            },
        )
        remaining = editor.loc[
            ~editor["移除"].fillna(False).astype(bool), "id"
        ].tolist()
        if remaining != selected_ids:
            st.session_state[selected_key] = remaining
            st.rerun()
        note = st.text_input(
            "说明", value="三仓流程启用期初调拨",
            key="baseline_transfer_note",
        )
        total = int(pd.to_numeric(editor["本次调拨"], errors="coerce").fillna(0).sum())
        st.metric("本批调拨合计", f"{total:,} 件")
        if st.button(
            "确认补录期初调拨", type="primary", width="stretch",
            key="baseline_transfer_submit",
        ):
            if source == target:
                st.error("来源仓库和目标仓库不能相同。")
                return
            lines = [
                {"inventory_item_id": str(row["id"]), "quantity": int(row["本次调拨"])}
                for row in editor.to_dict("records")
                if not bool(row.get("移除")) and int(row.get("本次调拨") or 0) > 0
            ]
            if not lines:
                st.error("请至少填写一项实际调拨数量。")
                return
            try:
                record_transfer_baseline(
                    supabase, business_date, source, target, lines, note,
                    get_current_operator_name(),
                )
            except Exception as exc:
                if "record_inventory_transfer_baseline" in str(exc):
                    st.error(
                        "期初调拨功能尚未初始化，请先运行仓库调拨第 5 个迁移脚本。"
                    )
                    return
                raise
            st.session_state[selected_key] = []
            _saved("期初调拨已补录；库存分布未重复变动。")


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
