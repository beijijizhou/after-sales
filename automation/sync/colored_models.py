"""Colored-shirt usage models, reconciliation backlog and wide tables."""

import pandas as pd

from automation.sync.colored_source import (
    load_daily_colored_production,
    load_daily_colored_production_source,
)
from db.inventory.core.constants import SIZE_COLUMNS
from utils.daily_usage_model import (
    EFFECTIVE_DAYS_GLOBAL_WINDOW,
    build_daily_usage_summary,
)


CATEGORY = "彩色短袖"


def load_colored_consumption_history(supabase, current_date, days=14):
    frames, observation_dates = [], []
    for offset in range(int(days)):
        target_date = current_date.fromordinal(current_date.toordinal() - offset)
        daily = load_daily_colored_production(target_date, require_complete=False)
        if daily.empty:
            continue
        daily = daily.copy()
        daily["日期"] = target_date
        daily["颜色"] = daily["颜色"].replace({"浅灰": "灰色"})
        frames.append(daily)
        observation_dates.append(target_date)
    columns = [
        "颜色", "尺码", "每日消耗", "有效天数", "自然日均消耗",
        "窗口总消耗", "窗口天数",
    ]
    if not frames:
        return pd.DataFrame(columns=columns)
    summary = build_daily_usage_summary(
        pd.concat(frames, ignore_index=True), ["颜色", "尺码"], "生产数量",
        current_date, days, date_column="日期",
        effective_day_mode=EFFECTIVE_DAYS_GLOBAL_WINDOW,
        observation_dates=observation_dates, usage_column="每日消耗",
        effective_days_column="有效天数", natural_usage_column="自然日均消耗",
        total_usage_column="窗口总消耗", window_days_column="窗口天数",
        round_digits=3,
    )
    return summary[columns]


def build_colored_reconciliation_backlog(
    supabase, current_date, days=14, *, load_deducted_total, build_preview,
):
    rows = []
    for offset in range(int(days)):
        movement_date = current_date.fromordinal(current_date.toordinal() - offset)
        source, metadata = load_daily_colored_production_source(movement_date)
        if source.empty:
            continue
        deducted = load_deducted_total(supabase, movement_date)
        if deducted <= 0:
            continue
        source_quantity = int(pd.to_numeric(
            source["生产数量"], errors="coerce"
        ).fillna(0).sum())
        remaining = max(source_quantity - deducted, 0)
        missing = tuple(metadata.get("missing_platforms") or ())
        if remaining <= 0 and not missing:
            continue
        preview = build_preview(supabase, movement_date)
        deductable = int(pd.to_numeric(
            preview.get("预计扣减", pd.Series(dtype="float64")), errors="coerce"
        ).fillna(0).sum())
        unresolved = max(remaining - deductable, 0)
        status = (
            "有库存差额可继续扣减" if deductable
            else "等待补库存或修正 SKU" if unresolved
            else "等待补齐平台数据"
        )
        rows.append({
            "日期": movement_date, "生产数据": source_quantity,
            "已扣库存": deducted, "当前可补扣": deductable,
            "库存/SKU待核对": unresolved,
            "尚未读取平台": "、".join(missing) or "无", "状态": status,
        })
    return pd.DataFrame(rows)


def build_colored_forecast_usage(history):
    columns = [
        "department", "category", "planning_material", "color", "size",
        "system_daily_usage",
    ]
    if history is None or history.empty:
        return pd.DataFrame(columns=columns)
    result = history.rename(columns={
        "颜色": "color", "尺码": "size", "每日消耗": "system_daily_usage",
    }).copy()
    result["department"] = "DTF"
    result["category"] = CATEGORY
    result["planning_material"] = "全部品牌/材质"
    return result[columns]


def build_colored_consumption_wide_table(display):
    columns = ["颜色", "指标", *SIZE_COLUMNS]
    if display is None or display.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for color in sorted(display["颜色"].dropna().astype(str).unique()):
        color_rows = display[display["颜色"].astype(str) == color]
        for field in ["每日消耗", "当前库存", "可撑天数"]:
            values = color_rows.groupby("尺码", dropna=False)[field].sum(
                min_count=1
            ).to_dict()
            row = {"颜色": color, "指标": field}
            for size in SIZE_COLUMNS:
                value = values.get(size)
                row[size] = round(float(value), 1) if pd.notna(value) else None
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)
