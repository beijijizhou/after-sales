from zoneinfo import ZoneInfo

import pandas as pd

from db.barcode_operations import normalize_barcode
from db.supabase_client import supabase
from utils.barcode_patterns import build_barcode_candidates


NY_TIMEZONE = ZoneInfo("America/New_York")


def load_operation_history(start_at, end_at):
    response = (
        supabase.table("barcode_operation_history")
        .select("id,barcode,platform,operation_type,requires_rescan,created_by,created_at")
        .gte("created_at", start_at.isoformat())
        .lt("created_at", end_at.isoformat())
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    return response.data


def load_pending_operations():
    response = (
        supabase.table("barcode_operation_history")
        .select("id,barcode,platform,operation_type,requires_rescan,created_by,created_at")
        .eq("requires_rescan", True)
        .order("created_at", desc=True)
        .limit(5000)
        .execute()
    )
    return response.data


def load_history_by_barcodes(barcodes):
    rows = []
    normalized = list(dict.fromkeys(normalize_barcode(value) for value in barcodes))
    for index in range(0, len(normalized), 100):
        response = (
            supabase.table("barcode_operation_history")
            .select("id,barcode,platform,operation_type,requires_rescan,created_by,created_at")
            .in_("barcode", normalized[index:index + 100])
            .order("created_at")
            .execute()
        )
        rows.extend(response.data)
    return rows


def load_scans(barcodes):
    rows = []
    for index in range(0, len(barcodes), 100):
        response = (
            supabase.table("barcode_scans")
            .select("barcode,scanned_by,scanned_at")
            .in_("barcode", barcodes[index:index + 100])
            .order("scanned_at")
            .execute()
        )
        rows.extend(response.data)
    return rows


def build_operation_history(start_at, end_at):
    return build_history_from_rows(load_operation_history(start_at, end_at))


def build_barcode_histories_for_date(start_at, end_at):
    date_rows = load_operation_history(start_at, end_at)
    barcodes = list(dict.fromkeys(
        normalize_barcode(row.get("barcode", "")) for row in date_rows
    ))
    if not barcodes:
        return pd.DataFrame()
    full_history_df = build_history_from_rows(load_history_by_barcodes(barcodes))
    return aggregate_barcode_histories(full_history_df)


def build_pending_operation_history():
    history_df = build_history_from_rows(load_pending_operations())
    if history_df.empty:
        return history_df
    return history_df[history_df["状态"] == "待出库"].reset_index(drop=True)


def aggregate_barcode_histories(history_df):
    rows = []
    for barcode, group in history_df.groupby("单号 / 条码", sort=False):
        ordered = group.sort_values("标记时间")
        latest = ordered.iloc[-1]
        rows.append({
            "单号 / 条码": barcode,
            "平台": latest.get("平台", ""),
            "原质检人员": first_value(ordered["原质检人员"]),
            "原扫描时间": first_value(ordered["原扫描时间"]),
            "操作次数": len(ordered),
            "完整操作历史": "\n".join(
                f"{row['操作类型']}｜{row['标记人']}｜{row['标记时间']}"
                for _, row in ordered.iterrows()
            ),
            "当前状态": latest.get("状态", ""),
        })
    return pd.DataFrame(rows).sort_values("操作次数", ascending=False)


def first_value(values):
    nonempty = values.fillna("").astype(str)
    nonempty = nonempty[nonempty.str.strip() != ""]
    return nonempty.iloc[0] if not nonempty.empty else ""


def build_history_from_rows(rows):
    operations_df = pd.DataFrame(rows)
    if operations_df.empty:
        return pd.DataFrame()

    operations_df["barcode"] = operations_df["barcode"].apply(normalize_barcode)
    operations_df["created_at_dt"] = pd.to_datetime(
        operations_df["created_at"], errors="coerce", utc=True
    )
    operations_df["scan_candidates"] = operations_df["barcode"].apply(
        get_scan_candidates
    )
    barcodes = list(dict.fromkeys(
        candidate
        for candidates in operations_df["scan_candidates"]
        for candidate in candidates
    ))
    scans_df = normalize_scans(load_scans(barcodes))
    return combine_history(operations_df, scans_df)


def get_scan_candidates(barcode):
    normalized = normalize_barcode(barcode)
    candidates = [normalized, *build_barcode_candidates(normalized)]
    return list(dict.fromkeys(normalize_barcode(value) for value in candidates if value))


def normalize_scans(rows):
    scans_df = pd.DataFrame(rows)
    if scans_df.empty:
        return pd.DataFrame(columns=["barcode", "scanned_by", "scanned_at_dt"])
    scans_df["barcode"] = scans_df["barcode"].apply(normalize_barcode)
    scans_df["scanned_at_dt"] = pd.to_datetime(
        scans_df["scanned_at"], errors="coerce", utc=True
    )
    return scans_df.dropna(subset=["scanned_at_dt"])


def combine_history(operations_df, scans_df):
    rows = []
    for _, operation in operations_df.iterrows():
        barcode_scans = scans_df[
            scans_df["barcode"].isin(operation["scan_candidates"])
        ]
        earlier = barcode_scans[
            barcode_scans["scanned_at_dt"] <= operation["created_at_dt"]
        ].sort_values("scanned_at_dt", ascending=False)
        later = barcode_scans[
            barcode_scans["scanned_at_dt"] > operation["created_at_dt"]
        ].sort_values("scanned_at_dt")
        original_scan = earlier.iloc[0] if not earlier.empty else None
        next_scan = later.iloc[0] if not later.empty else None
        rows.append(build_history_row(operation, original_scan, next_scan))

    return pd.DataFrame(rows).sort_values("标记时间", ascending=False)


def build_history_row(operation, original_scan, next_scan):
    return {
        "单号 / 条码": operation["barcode"],
        "平台": operation.get("platform", "") or "",
        "操作类型": operation["operation_type"],
        "原质检人员": scan_value(original_scan, "scanned_by"),
        "原扫描时间": format_ny_datetime(scan_value(original_scan, "scanned_at_dt")),
        "标记人": operation.get("created_by", ""),
        "标记时间": format_ny_datetime(operation["created_at_dt"]),
        "后续扫描条码": scan_value(next_scan, "barcode"),
        "后续扫描人员": scan_value(next_scan, "scanned_by"),
        "后续扫描时间": format_ny_datetime(scan_value(next_scan, "scanned_at_dt")),
        "需要重扫": "是" if operation.get("requires_rescan", True) else "否",
        "状态": "已重新出库" if next_scan is not None else "待出库",
    }


def scan_value(scan, column):
    return "" if scan is None else scan.get(column, "")


def format_ny_datetime(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return ""
    return parsed.tz_convert(NY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
