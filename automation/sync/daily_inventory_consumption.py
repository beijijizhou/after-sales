from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from automation.sync.dtf_colored_inventory import apply_colored_daily_deduction
from automation.sync.daily import COLORED_PRIMARY_PLATFORMS
from automation.sync.uv_daily_operation import apply_daily_sync
from automation.sync.daily_flow_preview import (
    load_flow_preview,
    uv_exclusion_note as _uv_exclusion_note,
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

COLORED_FAST_PLATFORM_SCOPE = "、".join(COLORED_PRIMARY_PLATFORMS)


def load_automatic_daily_previews(
    supabase, movement_date, sheets_client, spreadsheet_id, flows=None,
):
    previews = {}
    for flow in tuple(flows or AUTOMATIC_DAILY_FLOWS):
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
    ensure_colored_source=None, max_day_workers=2,
    report_day_progress=None,
):
    source_errors = _ensure_colored_sources(
        missing_dates, ensure_colored_source, max_day_workers,
        report_day_progress,
    )
    result = {}
    for movement_date in sorted(missing_dates):
        requested = str(missing_dates[movement_date])
        if report_day_progress:
            report_day_progress(
                movement_date, requested, "正在生成补录预览"
            )
        requested_flows = [
            flow for flow in AUTOMATIC_DAILY_FLOWS
            if flow.label in requested
        ]
        previews = load_automatic_daily_previews(
            supabase, movement_date, sheets_client, spreadsheet_id,
            flows=requested_flows,
        )
        if movement_date in source_errors and "彩色短袖" in requested:
            previews["colored"] = AutomaticDailyPreview(
                AUTOMATIC_DAILY_FLOWS[0], "error", 0, pd.DataFrame(),
                f"生产数据读取失败：{source_errors[movement_date]}",
            )
        result[movement_date] = {
            flow.code: previews[flow.code]
            for flow in AUTOMATIC_DAILY_FLOWS
            if flow.label in requested
        }
        if report_day_progress:
            final_state = (
                "生产数据读取失败"
                if movement_date in source_errors else "预览完成"
            )
            report_day_progress(
                movement_date, requested, final_state
            )
    return result


def _ensure_colored_sources(
    missing_dates, ensure_colored_source, max_day_workers,
    report_day_progress=None,
):
    if ensure_colored_source is None:
        return {}
    dates = [
        movement_date for movement_date in sorted(missing_dates)
        if "彩色短袖" in str(missing_dates[movement_date])
    ]
    if not dates:
        return {}
    errors = {}
    workers = max(1, min(int(max_day_workers), len(dates)))
    if report_day_progress:
        for movement_date in dates:
            report_day_progress(
                movement_date,
                str(missing_dates[movement_date]),
                "正在补齐生产数据",
            )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(ensure_colored_source, movement_date): movement_date
            for movement_date in dates
        }
        for future in as_completed(futures):
            movement_date = futures[future]
            try:
                future.result()
                if report_day_progress:
                    report_day_progress(
                        movement_date,
                        str(missing_dates[movement_date]),
                        "生产数据已就绪",
                    )
            except Exception as error:
                errors[movement_date] = str(error)
                if report_day_progress:
                    report_day_progress(
                        movement_date,
                        str(missing_dates[movement_date]),
                        "生产数据读取失败",
                    )
    return errors


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
                "数据范围": (
                    f"快速补录：{COLORED_FAST_PLATFORM_SCOPE}"
                    if flow.code == "colored" else "Google Sheets"
                ),
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
    return load_flow_preview(
        flow, supabase, movement_date, sheets_client, spreadsheet_id,
        AutomaticDailyPreview,
    )
