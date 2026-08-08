from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    build_colored_platform_audit,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
)
from automation.sync.daily import COLORED_PRIMARY_PLATFORMS
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
    if flow.code == "colored":
        deducted = load_colored_day_deducted_total(supabase, movement_date)
        rows = build_colored_daily_preview(supabase, movement_date)
        source_rows, source_metadata = build_colored_platform_audit(
            movement_date
        )
        source_quantity = int(pd.to_numeric(
            source_rows.get("原始生产件数", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0).sum())
        remaining_source = max(source_quantity - int(deducted), 0)
        if source_quantity and remaining_source == 0:
            return AutomaticDailyPreview(
                flow, "completed", int(deducted), pd.DataFrame(),
                "当天生产库存已全部扣减",
                source_rows, source_quantity, 0,
            )
        if rows.empty:
            state = "blocked" if remaining_source else "no_data"
            message = (
                f"剩余 {remaining_source:,} 件尚未匹配到可扣库存"
                if remaining_source else "当天暂无生产数据"
            )
            return AutomaticDailyPreview(
                flow, state, 0, rows, message,
                source_rows, source_quantity, remaining_source,
            )
        syncable = rows[rows["状态"] == "可扣减"]
        quantity = int(pd.to_numeric(
            syncable["预计扣减"], errors="coerce"
        ).fillna(0).sum())
        unresolved = max(remaining_source - quantity, 0)
        missing = tuple(source_metadata.get("missing_platforms") or ())
        included = set(source_metadata.get("included_platforms") or ())
        primary_complete = (
            source_metadata.get("colored_primary_complete") is True
            or set(COLORED_PRIMARY_PLATFORMS).issubset(included)
        )
        blocking_missing = () if primary_complete else missing
        coverage_note = (
            f"快速补录已覆盖{COLORED_FAST_PLATFORM_SCOPE}；"
            "其余平台留待全平台核对"
            if primary_complete and missing else ""
        )
        problems = []
        if unresolved:
            problems.append(f"有 {unresolved:,} 件尚未匹配到可扣库存")
        if blocking_missing:
            problems.append("缺少平台：" + "、".join(missing))
        if blocking_missing or (unresolved and quantity == 0):
            return AutomaticDailyPreview(
                flow, "blocked", quantity, rows, "；".join(problems),
                source_rows, source_quantity, unresolved,
            )
        if unresolved:
            message = (
                f"可先扣减 {quantity:,} 件；剩余 {unresolved:,} 件继续保留待处理"
            )
            if coverage_note:
                message += "；" + coverage_note
            return AutomaticDailyPreview(
                flow, "ready", quantity, rows, message,
                source_rows, source_quantity, unresolved,
            )
        return AutomaticDailyPreview(
            flow, "ready", quantity, rows, coverage_note, source_rows,
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
    excluded = rows[rows["状态"] == "待分配 SKU（本次不扣）"]
    exclusion_note = _uv_exclusion_note(excluded)
    blocking = rows[~rows["状态"].isin(SYNCABLE_STATUSES)]
    quantity = int(pd.to_numeric(
        rows["预计扣减"], errors="coerce"
    ).fillna(0).sum())
    if not blocking.empty:
        problems = "；".join(
            f"{row['表格产品']}：{row['状态']}"
            for row in blocking.to_dict("records")
        )
        message = "；".join(filter(None, [problems, exclusion_note]))
        return AutomaticDailyPreview(
            flow, "blocked", quantity, rows, message
        )
    return AutomaticDailyPreview(
        flow, "ready", quantity, rows, exclusion_note
    )


def _uv_exclusion_note(excluded_rows):
    if excluded_rows is None or excluded_rows.empty:
        return ""
    labels = []
    for row in excluded_rows.to_dict("records"):
        product = str(row.get("表格产品") or "未识别产品").strip()
        quantity = int(pd.to_numeric(
            pd.Series([row.get("当日消耗", 0)]), errors="coerce"
        ).fillna(0).iloc[0])
        product_label = f"{product}（手机壳）" if product == "Iphone" else product
        labels.append(f"{product_label} {quantity:,} 件")
    return "、".join(labels) + "未进入统计及库存扣减"
