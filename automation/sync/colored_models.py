"""Colored-shirt usage models, reconciliation backlog and wide tables."""

import pandas as pd

from automation.production_period import load_recent_production_model
from automation.sync.colored_source import (
    load_daily_colored_production_source,
)
from db.inventory.core.constants import SIZE_COLUMNS
from db.planning import build_daily_usage_contract, empty_daily_usage_contract
from utils.erp.inventory_mapping import KEY_COLUMNS


CATEGORY = "彩色短袖"
COLORED_REASON_PREFIX = "彩色短袖生产自动扣减 "


def load_colored_consumption_history(supabase, current_date, days=14):
    columns = [
        "颜色", "尺码", "每日消耗", "有效天数", "自然日均消耗",
        "窗口总消耗", "窗口天数",
    ]
    model = load_recent_production_model(
        current_date, int(days), CATEGORY, supabase
    )
    if model.data.empty:
        empty = pd.DataFrame(columns=columns)
        empty.attrs.update({"source": "empty", "ledger_dates": ()})
        return empty
    result = model.data.rename(columns={
        "平台生产日均": "每日消耗",
    }).copy()
    result["有效天数"] = int(model.effective_days)
    result["自然日均消耗"] = result["每日消耗"]
    result["窗口总消耗"] = (
        pd.to_numeric(result["每日消耗"], errors="coerce").fillna(0)
        * int(model.requested_days or days)
    )
    result["窗口天数"] = int(model.requested_days or days)
    result = result[columns]
    result.attrs.update({
        "source": "production_period",
        "ledger_dates": (),
    })
    return result


def load_colored_ledger_history(supabase, start_date, end_date):
    """Load active persisted colored deductions as a conservative model fallback."""
    columns = ["日期", "颜色", "尺码", "生产数量"]
    try:
        rows = (
            supabase.table("inventory_movements")
            .select(
                "movement_date,color,size,quantity_change,reason,"
                "batch_id,reversal_of_batch_id"
            )
            .eq("department", "DTF")
            .eq("category", CATEGORY)
            .gte("movement_date", start_date.isoformat())
            .lte("movement_date", end_date.isoformat())
            .execute().data
            or []
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    movements = pd.DataFrame(rows)
    if movements.empty:
        return pd.DataFrame(columns=columns)
    for column in ["reason", "batch_id", "reversal_of_batch_id"]:
        if column not in movements:
            movements[column] = None
    reversed_ids = set(
        movements["reversal_of_batch_id"].dropna().astype(str)
    )
    quantities = pd.to_numeric(
        movements.get("quantity_change"), errors="coerce"
    ).fillna(0)
    active = movements[
        movements["reversal_of_batch_id"].isna()
        & quantities.lt(0)
        & movements["reason"].fillna("").astype(str).str.startswith(
            COLORED_REASON_PREFIX
        )
    ].copy()
    if reversed_ids:
        active = active[
            ~active["batch_id"].fillna("").astype(str).isin(reversed_ids)
        ]
    if active.empty:
        return pd.DataFrame(columns=columns)
    active["日期"] = pd.to_datetime(
        active["movement_date"], errors="coerce"
    ).dt.date
    active["颜色"] = active["color"].fillna("").astype(str).str.strip()
    active["尺码"] = active["size"].fillna("").astype(str).str.strip().str.upper()
    active["生产数量"] = pd.to_numeric(
        active["quantity_change"], errors="coerce"
    ).fillna(0).abs()
    return active.groupby(
        ["日期", "颜色", "尺码"], as_index=False
    )["生产数量"].sum()[columns]


def build_colored_reconciliation_backlog(
    supabase, current_date, days=14, *, load_deducted_total, build_preview,
):
    rows = []
    for offset in range(int(days)):
        movement_date = current_date.fromordinal(current_date.toordinal() - offset)
        source, metadata = load_daily_colored_production_source(
            movement_date, supabase=supabase
        )
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
    if history is None or history.empty:
        return empty_daily_usage_contract(KEY_COLUMNS)
    result = history.rename(columns={
        "颜色": "color", "尺码": "size", "每日消耗": "system_daily_usage",
    }).copy()
    result["department"] = "DTF"
    result["category"] = CATEGORY
    result["planning_material"] = "全部品牌/材质"
    return build_daily_usage_contract(
        result,
        key_columns=KEY_COLUMNS,
        daily_usage_column="system_daily_usage",
        effective_days_column="有效天数",
        window_days_column="窗口天数",
        total_usage_column="窗口总消耗",
        source_type="production_api",
        source_label="彩色短袖平台生产",
    )


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
