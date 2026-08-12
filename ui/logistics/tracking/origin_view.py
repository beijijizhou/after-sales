"""USPS origin extraction and tracking-result presentation."""

import re

import pandas as pd
import streamlit as st


def render_results(frame):
    if frame.empty:
        st.warning("数据库和 USPS 接口都没有返回可显示的数据。")
        return
    columns = [
        "订单号", "tracking_number", "USPS子类型", "实际揽收方",
        "数据来源", "provider_status", "USPS面单创建地点", "始发地点判断",
        "发货地址", "重量（oz）", "重量（lb）", "面单OCR地址", "地址来源",
        "地址获取状态", "无法获取原因", "has_postal_record", "has_pre_scan",
        "USPS查询说明", "面单PDF",
    ]
    st.dataframe(
        frame[[column for column in columns if column in frame]],
        hide_index=True, width="stretch",
        column_config={
            "tracking_number": "Tracking Number",
            "provider_status": "USPS 状态",
            "has_postal_record": "存在邮政记录",
            "has_pre_scan": "已有预扫描/扫描",
            "面单PDF": st.column_config.LinkColumn(display_text="打开面单"),
        },
    )


def render_raw_responses(frame):
    rows = raw_response_rows(frame)
    if not rows:
        return
    with st.expander("查看 USPS 原始 API Response（JSON）"):
        st.caption("数据库优先模式显示上次保存的 USPS 响应；强制请求显示实时响应。")
        for tracking_number, payload in rows:
            st.markdown(f"**{tracking_number}**")
            st.json(payload, expanded=False)


def render_tracking_events(frame):
    events = tracking_event_rows(frame)
    if events:
        with st.expander(f"查看 USPS Tracking Events（{len(events)} 条）"):
            st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch")


def tracking_event_rows(frame):
    if frame.empty or "response_payload" not in frame:
        return []
    rows = []
    for item in frame.to_dict("records"):
        tracking_number = str(item.get("tracking_number") or "")
        payload = item.get("response_payload")
        if not isinstance(payload, dict):
            continue
        for event in payload.get("trackingEvents") or []:
            if not isinstance(event, dict):
                continue
            city = str(event.get("eventCity") or "").strip()
            state = str(event.get("eventState") or "").strip()
            postal = str(event.get("eventZIPCode") or "").strip()
            locality = ", ".join(value for value in (city, state) if value)
            rows.append({
                "Tracking Number": tracking_number,
                "事件代码": event.get("eventCode", ""),
                "事件类型": event.get("eventType", ""),
                "事件时间": event.get("eventTimestamp", ""),
                "事件地点": " ".join(
                    value for value in (locality, postal) if value
                ),
            })
    return rows


def raw_response_rows(frame):
    if frame.empty or "response_payload" not in frame:
        return []
    rows, seen = [], set()
    for item in frame.to_dict("records"):
        number = str(item.get("tracking_number") or "")
        payload = item.get("response_payload")
        if number and number not in seen and isinstance(payload, dict):
            rows.append((number, payload))
            seen.add(number)
    return rows


def apply_usps_origin_fallback(frame):
    if frame.empty or "response_payload" not in frame:
        return frame
    result = frame.copy()
    for index, row in result.iterrows():
        details = extract_usps_origin_details(row.get("response_payload"))
        origin = details.get("address", "")
        if not origin:
            continue
        result.at[index, "USPS面单创建地点"] = origin
        result.at[index, "始发地点判断"] = (
            "正常：纽约州" if details.get("state", "").upper() == "NY"
            else "异常：不是纽约工厂地址"
        )
        existing = str(row.get("发货地址") or "").strip()
        if existing and existing != "无法获取":
            result.at[index, "面单OCR地址"] = existing
        result.at[index, "发货地址"] = origin
        result.at[index, "地址来源"] = details.get("source", "USPS Tracking API")
        result.at[index, "地址获取状态"] = "已优先采用USPS接口始发地点"
        result.at[index, "无法获取原因"] = (
            "USPS Tracking不返回寄件街道；完整街道仅在面单可下载时由OCR补充"
        )
    return result


def extract_usps_origin(payload):
    return extract_usps_origin_details(payload).get("address", "")


def extract_usps_origin_details(payload):
    if not isinstance(payload, dict):
        return {}
    found = _find_explicit_origin(payload)
    if not found:
        found = _find_label_created_event(payload)
    if not found:
        return {}
    city, state, postal, source = found
    city, state, postal = (
        str(value or "").strip() for value in (city, state, postal)
    )
    locality = ", ".join(value for value in (city, state) if value)
    return {
        "address": " ".join(value for value in (locality, postal) if value),
        "city": city, "state": state, "postal_code": postal,
        "source": source,
    }


def _find_explicit_origin(value):
    if isinstance(value, list):
        return next((found for item in value
                     if (found := _find_explicit_origin(item))), None)
    if not isinstance(value, dict):
        return None
    fields = {
        re.sub(r"[^a-z]", "", str(key).casefold()): item
        for key, item in value.items()
    }
    city = fields.get("origincity")
    state = fields.get("originstate")
    postal = fields.get("originzipcode") or fields.get("originzip")
    if any((city, state, postal)):
        return city, state, postal, "USPS Tracking API（始发城市/州/ZIP）"
    origin = fields.get("originlocation")
    if isinstance(origin, dict):
        normalized = {
            re.sub(r"[^a-z]", "", str(key).casefold()): item
            for key, item in origin.items()
        }
        found = (
            normalized.get("city"), normalized.get("state"),
            normalized.get("zipcode") or normalized.get("zip")
            or normalized.get("postalcode"),
        )
        if any(found):
            return *found, "USPS Tracking API（始发城市/州/ZIP）"
    return next((found for item in value.values()
                 if (found := _find_explicit_origin(item))), None)


def _find_label_created_event(payload):
    for event in payload.get("trackingEvents") or []:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("eventType") or "").casefold()
        if str(event.get("eventCode") or "").upper() == "GX" or (
            "shipping label created" in event_type
        ):
            return (
                event.get("eventCity"), event.get("eventState"),
                event.get("eventZIPCode"),
                "USPS Tracking API（Shipping Label Created事件地点）",
            )
    return None
