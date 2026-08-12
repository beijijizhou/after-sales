"""Label detail loading and display-model construction."""

import pandas as pd
import streamlit as st

from automation.logistics import classify_usps_subtype, usps_pickup_name
from automation.logistics.label_ocr import extract_label_fields
from db.logistics import (
    load_latest_label_reviews,
    load_shipments_by_tracking,
    save_label_review,
)
from utils.auth import get_current_operator_name


def extract_live_label_details(context):
    if context.empty or "物流单号" not in context:
        return pd.DataFrame()
    rows = []
    for row in context.to_dict("records"):
        number = str(row.get("物流单号") or "").strip()
        status = str(row.get("OCR状态") or "").strip()
        if number and status:
            rows.append({
                "tracking_number": number,
                "发货地址": row.get("面单OCR地址") or "无法获取",
                "面单OCR地址": row.get("面单OCR地址") or "",
                "重量（oz）": row.get("重量（oz）"),
                "重量（lb）": row.get("重量（lb）"),
                "地址来源": "平台面单PDF（OCR）",
                "地址获取状态": status,
                "无法获取原因": "" if row.get("面单OCR地址") else status,
                "面单PDF": row.get("面单PDF") or row.get("备用面单PDF"),
            })
    return pd.DataFrame(rows)


def live_label_row(tracking_number, label_url, fields, status):
    address = _address(fields)
    return {
        "tracking_number": tracking_number,
        "发货地址": address or "无法获取",
        "面单OCR地址": address,
        "重量（oz）": fields.get("extracted_weight_oz"),
        "重量（lb）": fields.get("extracted_weight_lb"),
        "地址来源": "平台面单PDF（OCR）" if address else "平台面单PDF",
        "地址获取状态": status,
        "无法获取原因": "" if address else status,
        "面单PDF": label_url,
    }


def load_label_details(supabase, numbers, database_error):
    try:
        shipments = load_shipments_by_tracking(supabase, numbers)
        if shipments.empty:
            return pd.DataFrame([
                missing_label_row(number, "ERP未找到面单记录")
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
                review, failure = _load_and_save_review(supabase, shipment)
                if failure:
                    rows.append(label_display_row(shipment, {}, failure))
                    continue
            rows.append(label_display_row(shipment, review, "已从面单识别"))
            progress.progress(index / len(shipments))
        rows.extend(
            missing_label_row(number, "ERP未找到面单记录")
            for number in numbers if number not in found_numbers
        )
        progress.empty()
        return pd.DataFrame(rows)
    except Exception as error:
        st.error(database_error(error))
        return pd.DataFrame()


def _load_and_save_review(supabase, shipment):
    url = shipment.get("label_url") or shipment.get("backup_label_url")
    if not url:
        return {}, "平台未提供面单下载，无法获取完整发货地址"
    try:
        fields = extract_label_fields(url)
        saved = save_label_review(
            supabase, shipment["id"], dict(fields),
            get_current_operator_name(),
        )
        return (saved[0] if saved else fields), ""
    except Exception as error:
        return {}, f"OCR失败：{error}"


def label_display_row(shipment, review, status):
    address = _address(review)
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
        "重量（lb）": round(float(weight) / 16, 4) if weight is not None else None,
        "地址来源": "平台面单PDF（OCR）" if address else "无可用面单",
        "地址获取状态": status,
        "无法获取原因": "" if address else status,
        "面单PDF": shipment.get("label_url") or shipment.get("backup_label_url"),
    }


def missing_label_row(number, status):
    return {
        "tracking_number": number,
        "USPS子类型": "待确认", "实际揽收方": "待确认",
        "发货地址": "无法获取", "面单OCR地址": "",
        "重量（oz）": None, "重量（lb）": None,
        "地址来源": "无可用面单", "地址获取状态": status,
        "无法获取原因": status, "面单PDF": None,
    }


def merge_label_details(tracking, labels):
    if labels.empty:
        return tracking
    if tracking.empty:
        return labels
    return tracking.merge(labels, on="tracking_number", how="left")


def _address(fields):
    return " ".join(str(fields.get(field) or "").strip() for field in (
        "extracted_street", "extracted_city", "extracted_state",
        "extracted_postal_code",
    )).strip()
