import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from automation.logistics import (
    USPSClient,
    classify_usps_subtype,
    classify_usps_response,
    load_usps_credentials,
    usps_pickup_name,
)
from automation.logistics.label_ocr import extract_label_fields
from db.logistics import (
    load_latest_label_reviews,
    load_shipments_by_tracking,
    save_label_review,
)
from utils.auth import get_current_operator_name


def render_tracking_lookup(supabase, database_error):
    st.subheader("USPS物流单号接口查询")
    st.caption(
        "直接粘贴物流单号进行查询；支持换行、空格、逗号或分号分隔。"
    )
    raw = st.text_area(
        "物流单号",
        placeholder="每行一个物流单号，也可以直接粘贴一整列",
        key="logistics_tracking_lookup_input",
        height=180,
    )
    st.caption("当前为 USPS 实时接口模式；查询结果暂不写入数据库。")
    numbers = parse_tracking_numbers(raw)
    if not st.button(
        "开始查询", type="primary", disabled=not numbers,
        key="logistics_tracking_lookup_submit",
    ):
        st.info("粘贴物流单号后点击查询；结果仅用于当前页面，不写入数据库。")
        return

    fresh_rows = _query_usps(numbers)
    if fresh_rows is None:
        return

    display = pd.DataFrame(fresh_rows)
    if not display.empty:
        display["数据来源"] = "USPS 实时接口"
        display["USPS查询说明"] = display["has_postal_record"].map({
            True: "USPS已返回物流状态与Tracking Events",
            False: "USPS未发现物流记录",
        })

    summary = st.columns(2)
    summary[0].metric("输入面单号", len(numbers))
    summary[1].metric("USPS 实时查询", len(numbers))
    display = _apply_usps_origin_fallback(display)
    _render_results(display)
    _render_tracking_events(display)
    _render_raw_responses(display)


def _query_usps(numbers):
    if not numbers:
        return []
    try:
        credentials = load_usps_credentials(st.secrets)
        client = USPSClient(
            credentials["client_id"], credentials["client_secret"]
        )
        batches = [numbers[start:start + 35] for start in range(0, len(numbers), 35)]
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as executor:
            responses = list(executor.map(client.track, batches))
        rows = [
            classify_usps_response(item)
            for response in responses for item in response
        ]
        return rows
    except Exception as error:
        st.error(f"USPS 接口查询失败：{error}")
        return None


def _render_results(frame):
    if frame.empty:
        st.warning("数据库和 USPS 接口都没有返回可显示的数据。")
        return
    columns = [
        "tracking_number",
        "USPS子类型", "实际揽收方",
        "数据来源", "provider_status",
        "USPS面单创建地点", "始发地点判断", "发货地址", "重量（oz）",
        "面单OCR地址", "地址来源", "地址获取状态", "无法获取原因",
        "has_postal_record", "has_pre_scan", "USPS查询说明", "面单PDF",
    ]
    st.dataframe(
        frame[[column for column in columns if column in frame]],
        hide_index=True,
        width="stretch",
        column_config={
            "tracking_number": "Tracking Number",
            "provider_status": "USPS 状态",
            "has_postal_record": "存在邮政记录",
            "has_pre_scan": "已有预扫描/扫描",
            "面单PDF": st.column_config.LinkColumn(display_text="打开面单"),
        },
    )


def _render_raw_responses(frame):
    rows = _raw_response_rows(frame)
    if not rows:
        return
    with st.expander("查看 USPS 原始 API Response（JSON）"):
        st.caption(
            "数据库优先模式显示上次保存的 USPS 响应；强制请求模式显示本次实时响应。"
        )
        for tracking_number, payload in rows:
            st.markdown(f"**{tracking_number}**")
            st.json(payload, expanded=False)


def _render_tracking_events(frame):
    events = _tracking_event_rows(frame)
    if not events:
        return
    with st.expander(f"查看 USPS Tracking Events（{len(events)} 条）"):
        st.dataframe(
            pd.DataFrame(events), hide_index=True, width="stretch",
        )


def _tracking_event_rows(frame):
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


def _raw_response_rows(frame):
    if frame.empty or "response_payload" not in frame:
        return []
    rows = []
    seen = set()
    for item in frame.to_dict("records"):
        tracking_number = str(item.get("tracking_number") or "")
        payload = item.get("response_payload")
        if tracking_number and tracking_number not in seen and isinstance(payload, dict):
            rows.append((tracking_number, payload))
            seen.add(tracking_number)
    return rows


def _apply_usps_origin_fallback(frame):
    if frame.empty or "response_payload" not in frame:
        return frame
    result = frame.copy()
    for index, row in result.iterrows():
        details = _extract_usps_origin_details(row.get("response_payload"))
        origin = details.get("address", "")
        if origin:
            result.at[index, "USPS面单创建地点"] = origin
            result.at[index, "始发地点判断"] = (
                "正常：纽约州"
                if details.get("state", "").upper() == "NY"
                else "异常：不是纽约工厂地址"
            )
            existing_address = str(row.get("发货地址") or "").strip()
            if existing_address and existing_address != "无法获取":
                result.at[index, "面单OCR地址"] = existing_address
            result.at[index, "发货地址"] = origin
            result.at[index, "地址来源"] = details.get(
                "source", "USPS Tracking API"
            )
            result.at[index, "地址获取状态"] = "已优先采用USPS接口始发地点"
            result.at[index, "无法获取原因"] = (
                "USPS Tracking不返回寄件街道；完整街道仅在面单可下载时由OCR补充"
            )
            continue
        current_address = str(row.get("发货地址") or "").strip()
        if current_address and current_address != "无法获取":
            continue
        if not origin:
            continue
        result.at[index, "发货地址"] = origin
        result.at[index, "地址来源"] = details.get("source", "USPS Tracking API")
        result.at[index, "地址获取状态"] = "已从USPS接口取得面单创建地点"
        result.at[index, "无法获取原因"] = "USPS Tracking不返回寄件街道，仅返回始发地区"
    return result


def _extract_usps_origin(payload):
    return _extract_usps_origin_details(payload).get("address", "")


def _extract_usps_origin_details(payload):
    if not isinstance(payload, dict):
        return {}

    def normalized_map(value):
        return {
            re.sub(r"[^a-z]", "", str(key).casefold()): item
            for key, item in value.items()
        }

    def find_explicit_origin(value):
        if isinstance(value, dict):
            fields = normalized_map(value)
            city = fields.get("origincity")
            state = fields.get("originstate")
            postal = fields.get("originzipcode") or fields.get("originzip")
            if any((city, state, postal)):
                return city, state, postal, "USPS Tracking API（始发城市/州/ZIP）"
            origin = fields.get("originlocation")
            if isinstance(origin, dict):
                origin_fields = normalized_map(origin)
                city = origin_fields.get("city")
                state = origin_fields.get("state")
                postal = (
                    origin_fields.get("zipcode")
                    or origin_fields.get("zip")
                    or origin_fields.get("postalcode")
                )
                if any((city, state, postal)):
                    return city, state, postal, "USPS Tracking API（始发城市/州/ZIP）"
            for item in value.values():
                found = find_explicit_origin(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = find_explicit_origin(item)
                if found:
                    return found
        return None

    found = find_explicit_origin(payload)
    if not found:
        for event in payload.get("trackingEvents") or []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("eventType") or "").casefold()
            event_code = str(event.get("eventCode") or "").upper()
            if event_code == "GX" or "shipping label created" in event_type:
                found = (
                    event.get("eventCity"), event.get("eventState"),
                    event.get("eventZIPCode"),
                    "USPS Tracking API（Shipping Label Created事件地点）",
                )
                break
    if not found:
        return {}
    city, state, postal, source = found
    city, state, postal = (str(value or "").strip() for value in (city, state, postal))
    locality = ", ".join(value for value in (city, state) if value)
    return {
        "address": " ".join(value for value in (locality, postal) if value),
        "city": city, "state": state, "postal_code": postal,
        "source": source,
    }


def _load_label_details(supabase, numbers, database_error):
    try:
        shipments = load_shipments_by_tracking(supabase, numbers)
        if shipments.empty:
            return pd.DataFrame([
                _missing_label_row(number, "ERP未找到面单记录")
                for number in numbers
            ])
        reviews = load_latest_label_reviews(
            supabase, shipments["id"].astype(str).tolist()
        )
        review_by_shipment = (
            reviews.set_index("shipment_id").to_dict("index")
            if not reviews.empty else {}
        )
        rows = []
        found_numbers = set(shipments["tracking_number"].astype(str))
        progress = st.progress(0)
        for index, shipment in enumerate(shipments.to_dict("records"), start=1):
            review = review_by_shipment.get(str(shipment["id"]))
            if not review:
                url = shipment.get("label_url") or shipment.get("backup_label_url")
                if not url:
                    rows.append(_label_display_row(
                        shipment, {},
                        "平台未提供面单下载，无法获取完整发货地址",
                    ))
                    continue
                try:
                    fields = extract_label_fields(url)
                    saved = save_label_review(
                        supabase, shipment["id"], dict(fields),
                        get_current_operator_name(),
                    )
                    review = saved[0] if saved else fields
                except Exception as error:
                    rows.append(_label_display_row(
                        shipment, {}, f"OCR失败：{error}"
                    ))
                    continue
            rows.append(_label_display_row(shipment, review, "已从面单识别"))
            progress.progress(index / len(shipments))
        rows.extend(
            _missing_label_row(number, "ERP未找到面单记录")
            for number in numbers if number not in found_numbers
        )
        progress.empty()
    except Exception as error:
        st.error(database_error(error))
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _label_display_row(shipment, review, status):
    address = " ".join(str(review.get(field) or "").strip() for field in (
        "extracted_street", "extracted_city", "extracted_state",
        "extracted_postal_code",
    )).strip()
    weight = review.get("extracted_weight_oz")
    subtype = classify_usps_subtype(
        shipment.get("carrier"), shipment.get("tracking_number"),
        shipment.get("source_payload"),
    )
    return {
        "tracking_number": shipment.get("tracking_number", ""),
        "USPS子类型": subtype,
        "实际揽收方": usps_pickup_name(subtype),
        "发货地址": address or "无法获取",
        "面单OCR地址": address,
        "重量（oz）": weight,
        "地址来源": "平台面单PDF（OCR）" if address else "无可用面单",
        "地址获取状态": status,
        "无法获取原因": "" if address else status,
        "面单PDF": shipment.get("label_url") or shipment.get("backup_label_url"),
    }


def _missing_label_row(number, status):
    return {
        "tracking_number": number,
        "USPS子类型": "待确认",
        "实际揽收方": "待确认",
        "发货地址": "无法获取",
        "面单OCR地址": "",
        "重量（oz）": None,
        "地址来源": "无可用面单",
        "地址获取状态": status,
        "无法获取原因": status,
        "面单PDF": None,
    }


def _merge_label_details(tracking, labels):
    if labels.empty:
        return tracking
    if tracking.empty:
        return labels
    return tracking.merge(labels, on="tracking_number", how="left")


def parse_tracking_numbers(raw):
    parts = re.split(r"[,，;；\s]+", str(raw or ""))
    return list(dict.fromkeys(part.strip() for part in parts if part.strip()))


def split_tracking_cache(numbers, latest, force_usps=False):
    if force_usps or latest.empty:
        return pd.DataFrame(), list(numbers)
    frame = latest.copy()
    expiry = pd.to_datetime(frame["cache_expires_at"], errors="coerce", utc=True)
    fresh = frame[expiry > datetime.now(timezone.utc)]
    cached_numbers = set(fresh["tracking_number"].astype(str))
    pending = [number for number in numbers if number not in cached_numbers]
    return fresh, pending
