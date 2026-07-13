from db.barcode_operation_tracking import format_ny_datetime, load_history_by_barcodes
from db.barcode_operations import normalize_barcode


def enrich_search_with_operation_history(df):
    if df.empty or "barcode" not in df.columns:
        return df

    result_df = df.copy()
    result_df["barcode"] = result_df["barcode"].apply(normalize_barcode)
    grouped = {}
    for row in load_history_by_barcodes(result_df["barcode"]):
        barcode = normalize_barcode(row.get("barcode", ""))
        grouped.setdefault(barcode, []).append({
            "操作类型": row.get("operation_type", ""),
            "操作人": row.get("created_by", ""),
            "操作时间": format_ny_datetime(row.get("created_at")),
        })

    result_df["操作次数"] = result_df["barcode"].map(
        lambda barcode: len(grouped.get(barcode, []))
    )
    result_df["完整操作历史"] = result_df["barcode"].map(
        lambda barcode: format_operation_timeline(grouped.get(barcode, []))
    )
    return result_df


def format_operation_timeline(history):
    if not history:
        return "无操作记录"
    return "\n".join(
        f"{item['操作类型']}｜{item['操作人']}｜{item['操作时间']}"
        for item in history
    )
