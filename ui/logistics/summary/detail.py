"""Order-level drill-down for a logistics summary row."""

import pandas as pd

from ui.logistics.summary.model import (
    SCOPE_COLUMNS,
    _shipment_scope,
    _tracking_activity,
)


def build_platform_activity_detail(
    selected, shipments, checks, sources, reviews,
):
    detail = pd.concat([
        _erp_detail(selected, shipments),
        _tracking_detail(selected, checks, sources),
    ], ignore_index=True)
    if detail.empty:
        return detail
    if not reviews.empty and "shipment_id" in reviews:
        latest = reviews.drop_duplicates("shipment_id", keep="first").rename(
            columns={
                "shipment_id": "_shipment_id", "ocr_status": "OCR状态",
                "extracted_street": "OCR街道", "extracted_city": "OCR城市",
                "extracted_state": "OCR州", "extracted_postal_code": "OCR邮编",
                "extracted_weight_oz": "OCR重量（oz）",
            }
        )
        detail = detail.merge(latest, on="_shipment_id", how="left")
    for column in (
        "OCR状态", "OCR街道", "OCR城市", "OCR州", "OCR邮编", "OCR重量（oz）",
    ):
        if column not in detail:
            detail[column] = "" if column != "OCR重量（oz）" else None
    detail["OCR地址"] = detail[[
        "OCR街道", "OCR城市", "OCR州", "OCR邮编",
    ]].fillna("").astype(str).agg(" ".join, axis=1).str.replace(
        r"\s+", " ", regex=True
    ).str.strip()
    detail["记录时间"] = pd.to_datetime(
        detail["记录时间"], errors="coerce", utc=True
    ).dt.tz_convert("America/New_York")
    return detail.sort_values(
        ["记录时间", "ERP订单号", "物流单号"], ascending=[False, True, True]
    ).reset_index(drop=True)


def _erp_detail(selected, shipments):
    if shipments.empty:
        return pd.DataFrame()
    frame = _scope_filter(_shipment_scope(shipments), selected)
    if frame.empty:
        return frame
    return pd.DataFrame({
        "记录时间": frame["last_seen_at"], "记录类型": "ERP读取",
        "部门": frame["部门"], "平台": frame["平台"],
        "ERP账号": frame["ERP账号"], "ERP订单号": frame["external_order_id"],
        "商户订单号": frame["merchant_order_id"],
        "物流单号": frame["tracking_number"], "物流商": frame["carrier"],
        "USPS状态": "", "查询用户": "", "查询错误": "",
        "面单PDF": frame["label_url"].combine_first(frame["backup_label_url"]),
        "_shipment_id": frame["id"].astype(str),
    })


def _tracking_detail(selected, checks, sources):
    activity = _scope_filter(_tracking_activity(checks, sources), selected)
    if activity.empty:
        return activity
    return pd.DataFrame({
        "记录时间": activity["checked_at"], "记录类型": "USPS查询",
        "部门": activity["部门"], "平台": activity["平台"],
        "ERP账号": activity["ERP账号"],
        "ERP订单号": activity["external_order_id"],
        "商户订单号": activity["merchant_order_id"],
        "物流单号": activity["tracking_number"], "物流商": "USPS",
        "USPS状态": activity["provider_status"],
        "查询用户": activity["created_by"], "查询错误": activity["error_code"],
        "面单PDF": activity["label_url"].combine_first(
            activity["backup_label_url"]
        ),
        "_shipment_id": activity["shipment_id"].fillna("").astype(str),
    })


def _scope_filter(frame, selected):
    if frame.empty:
        return frame
    mask = pd.Series(True, index=frame.index)
    for column in SCOPE_COLUMNS:
        mask &= frame[column].astype(str) == str(selected[column])
    return frame.loc[mask].copy()
