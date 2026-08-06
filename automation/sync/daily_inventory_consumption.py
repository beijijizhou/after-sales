from dataclasses import dataclass

import pandas as pd

from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    build_colored_platform_audit,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
)
from automation.sync.uv_daily_operation import (
    SYNCABLE_STATUSES,
    apply_daily_sync,
    build_daily_sync_preview,
)
from automation.sync.uv_sheet_inventory import load_daily_summary
from db.inventory.core.queries import load_inventory_items
from db.inventory.operations.outbound_audit import (
    load_uv_daily_consumption_total,
)


@dataclass(frozen=True)
class AutomaticDailyFlow:
    code: str
    label: str


@dataclass
class AutomaticDailyPreview:
    flow: AutomaticDailyFlow
    state: str
    quantity: int
    rows: pd.DataFrame
    message: str = ""
    source_rows: pd.DataFrame | None = None
    source_quantity: int = 0
    unresolved_quantity: int = 0


AUTOMATIC_DAILY_FLOWS = (
    AutomaticDailyFlow("colored", "彩色短袖"),
    AutomaticDailyFlow("uv", "UV 生产库存"),
)


def load_automatic_daily_previews(
    supabase, movement_date, sheets_client, spreadsheet_id,
):
    previews = {}
    for flow in AUTOMATIC_DAILY_FLOWS:
        try:
            previews[flow.code] = _load_flow_preview(
                flow, supabase, movement_date, sheets_client, spreadsheet_id
            )
        except Exception as error:
            previews[flow.code] = AutomaticDailyPreview(
                flow, "error", 0, pd.DataFrame(), str(error)
            )
    return previews


def apply_automatic_daily_previews(
    supabase, movement_date, previews, created_by,
):
    results, errors = {}, {}
    for flow in AUTOMATIC_DAILY_FLOWS:
        preview = previews.get(flow.code)
        if preview is None or preview.state != "ready":
            continue
        try:
            if flow.code == "colored":
                quantity = apply_colored_daily_deduction(
                    supabase, preview.rows, movement_date, created_by
                )
            else:
                imported, _skipped = apply_daily_sync(
                    supabase, preview.rows, movement_date, created_by
                )
                quantity = imported
            results[flow.code] = int(quantity)
        except Exception as error:
            errors[flow.code] = str(error)
    return results, errors


def load_automatic_daily_batch_previews(
    supabase, missing_dates, sheets_client, spreadsheet_id,
):
    result = {}
    for movement_date in sorted(missing_dates):
        previews = load_automatic_daily_previews(
            supabase, movement_date, sheets_client, spreadsheet_id
        )
        requested = str(missing_dates[movement_date])
        result[movement_date] = {
            flow.code: previews[flow.code]
            for flow in AUTOMATIC_DAILY_FLOWS
            if flow.label in requested
        }
    return result


def build_automatic_daily_batch_summary(previews_by_date):
    rows = []
    for movement_date in sorted(previews_by_date):
        previews = previews_by_date[movement_date]
        for flow in AUTOMATIC_DAILY_FLOWS:
            preview = previews.get(flow.code)
            if preview is None:
                continue
            rows.append({
                "日期": movement_date,
                "项目": flow.label,
                "状态": preview.state,
                "预计扣减": int(preview.quantity),
                "来源总量": int(preview.source_quantity or preview.quantity),
                "待核对差额": int(preview.unresolved_quantity),
                "说明": preview.message,
            })
    return pd.DataFrame(rows)


def apply_automatic_daily_batch_previews(
    supabase, previews_by_date, created_by,
):
    results, errors = {}, {}
    for movement_date in sorted(previews_by_date):
        day_results, day_errors = apply_automatic_daily_previews(
            supabase,
            movement_date,
            previews_by_date[movement_date],
            created_by,
        )
        results.update({
            (movement_date, code): quantity
            for code, quantity in day_results.items()
        })
        errors.update({
            (movement_date, code): message
            for code, message in day_errors.items()
        })
    return results, errors


def _load_flow_preview(
    flow, supabase, movement_date, sheets_client, spreadsheet_id,
):
    if flow.code == "colored":
        deducted = load_colored_day_deducted_total(supabase, movement_date)
        if deducted:
            return AutomaticDailyPreview(
                flow, "completed", int(deducted), pd.DataFrame(),
                "当天已经扣减",
            )
        rows = build_colored_daily_preview(supabase, movement_date)
        source_rows, source_metadata = build_colored_platform_audit(
            movement_date
        )
        if rows.empty:
            return AutomaticDailyPreview(
                flow, "no_data", 0, rows, "当天暂无生产数据",
                source_rows=source_rows,
            )
        syncable = rows[rows["状态"] == "可扣减"]
        quantity = int(pd.to_numeric(
            syncable["预计扣减"], errors="coerce"
        ).fillna(0).sum())
        source_quantity = int(pd.to_numeric(
            source_rows.get("原始生产件数", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0).sum())
        unresolved = max(source_quantity - quantity, 0)
        missing = tuple(source_metadata.get("missing_platforms") or ())
        problems = []
        if unresolved:
            problems.append(f"有 {unresolved:,} 件尚未匹配到可扣库存")
        if missing:
            problems.append("缺少平台：" + "、".join(missing))
        if problems:
            return AutomaticDailyPreview(
                flow, "blocked", quantity, rows, "；".join(problems),
                source_rows, source_quantity, unresolved,
            )
        return AutomaticDailyPreview(
            flow, "ready", quantity, rows, "", source_rows,
            source_quantity, 0,
        )

    deducted = load_uv_daily_consumption_total(supabase, movement_date)
    if deducted:
        return AutomaticDailyPreview(
            flow, "completed", int(deducted), pd.DataFrame(),
            "当天已经扣减",
        )
    if sheets_client is None:
        raise ValueError("Google Sheets 服务账号不可用")
    summary = load_daily_summary(
        sheets_client, spreadsheet_id, movement_date
    )
    if not summary:
        return AutomaticDailyPreview(
            flow, "no_data", 0, pd.DataFrame(), "当天表格暂无消耗数据"
        )
    inventory = load_inventory_items(supabase, "UV", "")
    rows = build_daily_sync_preview(
        supabase, summary, movement_date, inventory
    )
    blocking = rows[~rows["状态"].isin(SYNCABLE_STATUSES)]
    quantity = int(pd.to_numeric(
        rows["预计扣减"], errors="coerce"
    ).fillna(0).sum())
    if not blocking.empty:
        message = "；".join(
            f"{row['表格产品']}：{row['状态']}"
            for row in blocking.to_dict("records")
        )
        return AutomaticDailyPreview(
            flow, "blocked", quantity, rows, message
        )
    return AutomaticDailyPreview(flow, "ready", quantity, rows)
