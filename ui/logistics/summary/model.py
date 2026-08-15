"""Daily logistics summary table model."""

import pandas as pd


SCOPE_COLUMNS = ["日期", "部门", "平台", "ERP账号"]
COUNT_COLUMNS = [
    "ERP记录数", "ERP订单数", "物流单号数", "PDF面单数", "OCR记录数",
    "USPS查询次数", "USPS查询单号", "USPS成功", "USPS失败",
]


def build_daily_platform_summary(shipments, checks, sources, reviews):
    erp = _erp_summary(shipments, reviews)
    tracking = _tracking_summary(checks, sources)
    if erp.empty:
        result = tracking
    elif tracking.empty:
        result = erp
    else:
        result = erp.merge(tracking, on=SCOPE_COLUMNS, how="outer")
    if result.empty:
        return pd.DataFrame(columns=[*SCOPE_COLUMNS, *COUNT_COLUMNS])
    for column in COUNT_COLUMNS:
        if column not in result:
            result[column] = 0
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    return result[[*SCOPE_COLUMNS, *COUNT_COLUMNS]].sort_values(
        ["日期", "部门", "平台", "ERP账号"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def _erp_summary(shipments, reviews):
    if shipments.empty:
        return pd.DataFrame()
    frame = _shipment_scope(shipments)
    reviewed_ids = _reviewed_shipment_ids(reviews)
    frame["_has_pdf"] = frame["label_url"].fillna("").astype(str).ne("") | (
        frame["backup_label_url"].fillna("").astype(str).ne("")
    )
    frame["_has_ocr"] = frame["id"].astype(str).isin(reviewed_ids)
    frame["_order"] = frame["external_order_id"].replace("", pd.NA)
    frame["_tracking"] = frame["tracking_number"].replace("", pd.NA)
    return frame.groupby(SCOPE_COLUMNS, dropna=False, as_index=False).agg(
        ERP记录数=("id", "nunique"),
        ERP订单数=("_order", "nunique"),
        物流单号数=("_tracking", "nunique"),
        PDF面单数=("_has_pdf", "sum"),
        OCR记录数=("_has_ocr", "sum"),
    )


def _tracking_summary(checks, sources):
    activity = _tracking_activity(checks, sources)
    if activity.empty:
        return pd.DataFrame()
    activity["_success"] = activity["has_postal_record"].fillna(False).astype(bool)
    activity["_failure"] = ~activity["_success"] | (
        activity["error_code"].fillna("").astype(str).ne("")
    )
    grouped = []
    for keys, rows in activity.groupby(SCOPE_COLUMNS, dropna=False):
        grouped.append({
            **dict(zip(SCOPE_COLUMNS, keys)),
            "USPS查询次数": rows["check_id"].nunique(),
            "USPS查询单号": rows["tracking_number"].nunique(),
            "USPS成功": rows.loc[rows["_success"], "check_id"].nunique(),
            "USPS失败": rows.loc[rows["_failure"], "check_id"].nunique(),
        })
    return pd.DataFrame(grouped)


def _shipment_scope(shipments):
    frame = shipments.copy()
    frame["日期"] = _ny_dates(frame["last_seen_at"])
    frame["部门"] = frame["department"].fillna("").replace("", "未设置")
    frame["平台"] = frame["erp_platform"].fillna("").replace("", "未设置")
    frame["ERP账号"] = frame["erp_account"].fillna("").replace("", "未设置")
    return frame


def _tracking_activity(checks, sources):
    if checks.empty:
        return pd.DataFrame()
    check_frame = checks.rename(columns={"id": "check_id"}).copy()
    if sources.empty:
        activity = check_frame.copy()
    else:
        activity = check_frame.merge(sources, on="check_id", how="left")
    activity["日期"] = _ny_dates(activity["checked_at"])
    activity["部门"] = _column(activity, "department").fillna("").replace(
        "", "未归属"
    )
    activity["平台"] = _column(activity, "erp_platform").fillna("").replace(
        "", "未归属"
    )
    activity["ERP账号"] = _column(activity, "erp_account").fillna("").replace(
        "", "未归属"
    )
    for column in (
        "shipment_id", "external_order_id", "merchant_order_id",
        "label_url", "backup_label_url", "provider_status", "error_code",
        "created_by",
    ):
        if column not in activity:
            activity[column] = ""
    return activity


def _reviewed_shipment_ids(reviews):
    if reviews.empty:
        return set()
    status = reviews.get("ocr_status", pd.Series("", index=reviews.index))
    result = reviews.get("automatic_result", pd.Series("", index=reviews.index))
    return set(reviews.loc[
        status.astype(str).eq("已识别") | result.astype(str).eq("OCR已识别"),
        "shipment_id",
    ].astype(str))


def _ny_dates(values):
    return pd.to_datetime(values, errors="coerce", utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.date


def _column(frame, name):
    return frame[name] if name in frame else pd.Series("", index=frame.index)
