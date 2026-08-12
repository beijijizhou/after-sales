import pandas as pd
import streamlit as st

from automation.logistics import classify_usps_subtype, usps_pickup_name
from db.logistics import load_all_shipments_by_tracking
from ui.logistics.tracking.input import parse_tracking_numbers


def render_reverse_lookup(supabase, database_error):
    st.subheader("物流单号反查订单")
    st.caption(
        "一个物流单号可能关联多个订单；结果不会按物流单号去重。"
    )
    raw = st.text_area(
        "物流单号列表",
        placeholder="每行一个物流单号，也可以直接粘贴一列",
        key="logistics_reverse_tracking_input",
    )
    numbers = parse_tracking_numbers(raw)
    if not st.button(
        "开始反查", type="primary", disabled=not numbers,
        key="logistics_reverse_submit",
    ):
        st.info("请先在“ERP订单获取”中同步需要核查的订单阶段和日期范围。")
        return
    try:
        frame = load_all_shipments_by_tracking(supabase, numbers)
    except Exception as error:
        st.error(database_error(error))
        return

    found = set(frame.get("tracking_number", pd.Series(dtype=str)).astype(str))
    missing = [number for number in numbers if number not in found]
    metrics = st.columns(3)
    metrics[0].metric("输入物流单号", len(numbers))
    metrics[1].metric("关联订单", len(frame))
    metrics[2].metric("未找到物流单号", len(missing))
    if missing:
        with st.expander("查看未找到的物流单号"):
            st.code("\n".join(missing), language=None)
    _render_order_matches(frame)


def _render_order_matches(frame):
    if frame.empty:
        st.warning("当前数据库没有找到关联订单。")
        return
    display = frame.copy()
    display["USPS子类型"] = display.apply(
        lambda row: classify_usps_subtype(
            row.get("carrier"), row.get("tracking_number"),
            row.get("source_payload"),
        ), axis=1,
    )
    display["实际揽收方"] = display["USPS子类型"].map(usps_pickup_name)
    display = display.rename(columns={
        "erp_platform": "ERP", "erp_account": "账号",
        "department": "部门", "external_order_id": "订单号",
        "merchant_order_id": "销售订单号",
        "tracking_number": "物流单号", "carrier": "物流商",
        "erp_status": "ERP阶段", "label_url": "面单PDF",
        "last_seen_at": "最近同步时间",
    })
    columns = [
        "物流单号", "ERP", "账号", "部门", "订单号", "销售订单号",
        "ERP阶段", "物流商", "USPS子类型", "实际揽收方",
        "最近同步时间", "面单PDF",
    ]
    st.dataframe(
        display[[column for column in columns if column in display]],
        hide_index=True, width="stretch",
        column_config={
            "面单PDF": st.column_config.LinkColumn(display_text="打开面单"),
        },
    )
