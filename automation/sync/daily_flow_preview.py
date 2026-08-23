"""Build one automatic inventory-deduction source preview."""

import pandas as pd

from automation.sync.daily import COLORED_PRIMARY_PLATFORMS
from automation.sync.dtf_colored_inventory import (
    build_colored_daily_preview,
    build_colored_platform_audit,
    load_colored_day_deducted_total,
)
from automation.sync.uv_daily_operation import (
    PHONE_CASE_PENDING_STATUS,
    SYNCABLE_STATUSES,
    build_daily_sync_preview,
)
from automation.sync.uv_sheet_inventory import load_daily_summary
from db.inventory.core.queries import load_inventory_items
from db.inventory.operations.outbound_audit import load_uv_daily_consumption_total


def load_flow_preview(
    flow, supabase, movement_date, sheets_client, spreadsheet_id, preview_type,
):
    if flow.code == "colored":
        return _colored_preview(flow, supabase, movement_date, preview_type)
    return _uv_preview(
        flow, supabase, movement_date, sheets_client, spreadsheet_id,
        preview_type,
    )


def _colored_preview(flow, supabase, movement_date, preview_type):
    deducted = load_colored_day_deducted_total(supabase, movement_date)
    rows = build_colored_daily_preview(supabase, movement_date)
    source_rows, metadata = build_colored_platform_audit(
        movement_date, supabase=supabase
    )
    source_quantity = int(pd.to_numeric(
        source_rows.get("原始生产件数", pd.Series(dtype="float64")),
        errors="coerce",
    ).fillna(0).sum())
    remaining = max(source_quantity - int(deducted), 0)
    if source_quantity and remaining == 0:
        return preview_type(
            flow, "completed", int(deducted), pd.DataFrame(),
            "当天生产库存已全部扣减", source_rows, source_quantity, 0,
        )
    if rows.empty:
        state = "blocked" if remaining else "no_data"
        message = (
            f"剩余 {remaining:,} 件尚未匹配到可扣库存"
            if remaining else "当天暂无生产数据"
        )
        return preview_type(
            flow, state, 0, rows, message, source_rows, source_quantity, remaining,
        )
    syncable = rows[rows["状态"] == "可扣减"]
    quantity = int(pd.to_numeric(
        syncable["预计扣减"], errors="coerce"
    ).fillna(0).sum())
    unresolved = max(remaining - quantity, 0)
    missing = tuple(metadata.get("missing_platforms") or ())
    included = set(metadata.get("included_platforms") or ())
    primary_complete = (
        metadata.get("colored_primary_complete") is True
        or set(COLORED_PRIMARY_PLATFORMS).issubset(included)
    )
    blocking_missing = () if primary_complete else missing
    coverage_note = (
        "快速补录已覆盖" + "、".join(COLORED_PRIMARY_PLATFORMS)
        + "；其余平台留待全平台核对"
        if primary_complete and missing else ""
    )
    problems = []
    if unresolved:
        problems.append(f"有 {unresolved:,} 件尚未匹配到可扣库存")
    if blocking_missing:
        problems.append("缺少平台：" + "、".join(missing))
    if blocking_missing or (unresolved and quantity == 0):
        return preview_type(
            flow, "blocked", quantity, rows, "；".join(problems),
            source_rows, source_quantity, unresolved,
        )
    message = ""
    if unresolved:
        message = f"可先扣减 {quantity:,} 件；剩余 {unresolved:,} 件继续保留待处理"
    if coverage_note:
        message = "；".join(filter(None, [message, coverage_note]))
    return preview_type(
        flow, "ready", quantity, rows, message,
        source_rows, source_quantity, unresolved,
    )


def _uv_preview(
    flow, supabase, movement_date, sheets_client, spreadsheet_id, preview_type,
):
    deducted = load_uv_daily_consumption_total(supabase, movement_date)
    if deducted:
        return preview_type(
            flow, "completed", int(deducted), pd.DataFrame(), "当天已经扣减"
        )
    if sheets_client is None:
        raise ValueError("Google Sheets 服务账号不可用")
    summary = load_daily_summary(sheets_client, spreadsheet_id, movement_date)
    if not summary:
        return preview_type(
            flow, "no_data", 0, pd.DataFrame(), "当天表格暂无消耗数据"
        )
    inventory = load_inventory_items(supabase, "UV", "")
    rows = build_daily_sync_preview(supabase, summary, movement_date, inventory)
    exclusion_note = uv_exclusion_note(
        rows[rows["状态"] == "待分配 SKU（本次不扣）"]
    )
    phone_note = phone_case_allocation_note(
        rows[rows["状态"] == PHONE_CASE_PENDING_STATUS]
    )
    blocking = rows[~rows["状态"].isin(SYNCABLE_STATUSES)]
    quantity = int(pd.to_numeric(rows["预计扣减"], errors="coerce").fillna(0).sum())
    if not blocking.empty:
        problems = "；".join(
            f"{row['表格产品']}：{row['状态']}"
            for row in blocking.to_dict("records")
        )
        return preview_type(
            flow, "blocked", quantity, rows,
            "；".join(filter(None, [problems, exclusion_note, phone_note])),
        )
    return preview_type(
        flow, "ready", quantity, rows,
        "；".join(filter(None, [exclusion_note, phone_note])),
    )


def phone_case_allocation_note(rows):
    if rows is None or rows.empty:
        return ""
    quantity = int(pd.to_numeric(
        rows["当日消耗"], errors="coerce"
    ).fillna(0).sum())
    return (
        f"手机壳 {quantity:,} 件待按材质和型号分配；"
        "请到 UV 系统库存扣减的“手机壳”分类处理"
    )


def uv_exclusion_note(excluded_rows):
    if excluded_rows is None or excluded_rows.empty:
        return ""
    labels = []
    for row in excluded_rows.to_dict("records"):
        product = str(row.get("表格产品") or "未识别产品").strip()
        quantity = int(pd.to_numeric(
            pd.Series([row.get("当日消耗", 0)]), errors="coerce"
        ).fillna(0).iloc[0])
        label = f"{product}（手机壳）" if product == "Iphone" else product
        labels.append(f"{label} {quantity:,} 件")
    return "、".join(labels) + "未进入统计及库存扣减"
