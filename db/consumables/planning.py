from datetime import timedelta

import pandas as pd

from db.batches import filter_active_batch_records
from db.planning import build_daily_usage_contract, calculate_stock_plan
from utils.daily_usage_model import (
    EFFECTIVE_DAYS_PER_KEY_ACTIVITY,
    build_daily_usage_summary,
)


CONSUMABLE_LOOKBACK_DAYS = 14
DEFAULT_COVERAGE_DAYS = 14


def build_consumable_consumption_model(
    items_df,
    batches_df,
    movements_df,
    lookback_days=CONSUMABLE_LOOKBACK_DAYS,
    current_date=None,
):
    columns = [
        "item_id", "分类", "耗材名称", "规格/型号", "品牌",
        "基础单位", "包装单位", "每箱数量", "最近领用日均", "有效数据天数",
        "自然窗口日均", "总领用量", "窗口天数",
        "当前库存", "当前库存（箱）", "最低库存", "最低库存（箱）",
    ]
    items = pd.DataFrame(items_df).copy()
    if items.empty or current_date is None:
        return pd.DataFrame(columns=columns)

    active_items = items[items["is_active"] == True].copy()
    if active_items.empty:
        return pd.DataFrame(columns=columns)

    issue_rows = _active_issue_movements(batches_df, movements_df)
    if issue_rows.empty:
        result = _base_item_frame(active_items)
        result["最近领用日均"] = 0.0
        result["有效数据天数"] = 0
        result["自然窗口日均"] = 0.0
        result["总领用量"] = 0.0
        result["窗口天数"] = max(int(lookback_days), 1)
        return result[columns]

    end_date = pd.Timestamp(current_date).date()
    start_date = end_date - timedelta(days=max(int(lookback_days), 1) - 1)
    issue_rows = issue_rows[
        issue_rows["movement_date"].between(start_date, end_date)
    ].copy()
    if issue_rows.empty:
        result = _base_item_frame(active_items)
        result["最近领用日均"] = 0.0
        result["有效数据天数"] = 0
        result["自然窗口日均"] = 0.0
        result["总领用量"] = 0.0
        result["窗口天数"] = max(int(lookback_days), 1)
        return result[columns]

    daily = issue_rows.rename(columns={"movement_date": "日期"}).copy()
    summary = build_daily_usage_summary(
        daily,
        ["item_id"],
        "issue_quantity",
        current_date,
        lookback_days,
        date_column="日期",
        effective_day_mode=EFFECTIVE_DAYS_PER_KEY_ACTIVITY,
        usage_column="最近领用日均",
        effective_days_column="有效数据天数",
        natural_usage_column="自然窗口日均",
        total_usage_column="总领用量",
        window_days_column="窗口天数",
        round_digits=2,
    )

    result = _base_item_frame(active_items).merge(
        summary, on="item_id", how="left"
    )
    result["最近领用日均"] = pd.to_numeric(
        result["最近领用日均"], errors="coerce"
    ).fillna(0.0)
    result["有效数据天数"] = pd.to_numeric(
        result["有效数据天数"], errors="coerce"
    ).fillna(0).astype(int)
    result["自然窗口日均"] = pd.to_numeric(
        result["自然窗口日均"], errors="coerce"
    ).fillna(0.0)
    result["总领用量"] = pd.to_numeric(
        result["总领用量"], errors="coerce"
    ).fillna(0.0)
    result["窗口天数"] = pd.to_numeric(
        result["窗口天数"], errors="coerce"
    ).fillna(max(int(lookback_days), 1)).astype(int)
    return result[columns]


def build_consumable_reorder_forecast(
    model_df,
    current_date=None,
    coverage_days=DEFAULT_COVERAGE_DAYS,
):
    columns = [
        "分类", "耗材名称", "规格/型号", "品牌",
        "库存基准总数", "库存基准日期", "当前日期",
        "预测日耗合计", "最低剩余天数", "预计最早耗尽日期",
        "最低库存", "安全库存缺口", "目标备货天数", "建议点货量",
        "建议点货量（箱）", "日耗依据", "有效数据天数",
        "自然窗口日均", "窗口天数",
    ]
    model = pd.DataFrame(model_df).copy()
    if model.empty or current_date is None:
        return pd.DataFrame(columns=columns)

    result = model.copy()
    result["库存基准总数"] = pd.to_numeric(
        result["当前库存"], errors="coerce"
    ).fillna(0.0)
    usage = build_consumable_forecast_usage(result)
    result = result.merge(
        usage[["item_id", "daily_usage"]], on="item_id", how="left"
    )
    result["预测日耗合计"] = pd.to_numeric(
        result["daily_usage"], errors="coerce"
    ).fillna(0.0)
    result["最低库存"] = pd.to_numeric(
        result["最低库存"], errors="coerce"
    ).fillna(0.0)
    result["有效数据天数"] = pd.to_numeric(
        result.get("有效数据天数"), errors="coerce"
    ).fillna(0).astype(int)
    result["自然窗口日均"] = pd.to_numeric(
        result.get("自然窗口日均"), errors="coerce"
    ).fillna(0.0)
    result["窗口天数"] = pd.to_numeric(
        result.get("窗口天数"), errors="coerce"
    ).fillna(CONSUMABLE_LOOKBACK_DAYS).astype(int)
    result["目标备货天数"] = int(max(coverage_days, 0))
    result["库存基准日期"] = current_date
    result["当前日期"] = current_date
    result["_stock_plan"] = result.apply(_stock_plan, axis=1)
    result["最低剩余天数"] = result["_stock_plan"].map(
        lambda plan: (
            int(plan.coverage_days)
            if plan.coverage_days is not None else pd.NA
        )
    )
    result["预计最早耗尽日期"] = result["最低剩余天数"].apply(
        lambda value: (
            current_date + timedelta(days=int(value))
            if pd.notna(value) else pd.NaT
        )
    )
    result["安全库存缺口"] = (
        result["最低库存"] - result["库存基准总数"]
    ).clip(lower=0)
    result["建议点货量"] = result["_stock_plan"].map(
        lambda plan: plan.reorder_quantity
    )
    result["建议点货量（箱）"] = result.apply(
        lambda row: (
            0
            if row["_stock_plan"].reorder_quantity <= 0
            else (
                row["_stock_plan"].reorder_packages
                if str(row.get("包装单位") or "").strip() == "箱"
                else pd.NA
            )
        ),
        axis=1,
    )
    result["日耗依据"] = result.apply(
        lambda row: (
            f"最近{int(row.get('窗口天数') or CONSUMABLE_LOOKBACK_DAYS)}天领用"
            if float(row["预测日耗合计"]) > 0
            else "暂无有效领用"
        ),
        axis=1,
    )
    result = result.sort_values(
        ["建议点货量", "最低剩余天数", "分类", "耗材名称", "规格/型号"],
        ascending=[False, True, True, True, True],
        kind="stable",
        na_position="last",
    )
    return result[columns].reset_index(drop=True)


def build_consumable_forecast_usage(model_df):
    """Adapt the consumable issue model to the shared usage contract."""

    return build_daily_usage_contract(
        model_df,
        key_columns=["item_id"],
        daily_usage_column="最近领用日均",
        effective_days_column="有效数据天数",
        window_days_column="窗口天数",
        total_usage_column="总领用量",
        source_type="warehouse_issue",
        source_label="每日耗材出库",
    )


def _active_issue_movements(batches_df, movements_df):
    batches = pd.DataFrame(batches_df).copy()
    movements = pd.DataFrame(movements_df).copy()
    columns = ["item_id", "movement_date", "issue_quantity"]
    if batches.empty or movements.empty:
        return pd.DataFrame(columns=columns)

    active_batches = filter_active_batch_records(
        batches, type_column="movement_type"
    )
    active_batches = active_batches[
        active_batches["movement_type"] == "issue"
    ].copy()
    if active_batches.empty:
        return pd.DataFrame(columns=columns)

    active_movements = filter_active_batch_records(
        movements,
        reversal_column="reversal_of_movement_id",
    )
    active_movements = active_movements[
        active_movements["batch_id"].astype(str).isin(
            active_batches["id"].astype(str)
        )
    ]
    if active_movements.empty:
        return pd.DataFrame(columns=columns)

    active_movements["movement_date"] = pd.to_datetime(
        active_movements["movement_date"], errors="coerce"
    ).dt.date
    active_movements["issue_quantity"] = pd.to_numeric(
        active_movements["quantity_change"], errors="coerce"
    ).fillna(0).abs()
    return active_movements[
        active_movements["movement_date"].notna()
        & (active_movements["issue_quantity"] > 0)
    ][columns].reset_index(drop=True)


def _base_item_frame(items_df):
    result = items_df.rename(columns={
        "id": "item_id",
        "category": "分类",
        "name": "耗材名称",
        "specification": "规格/型号",
        "brand": "品牌",
        "base_unit": "基础单位",
        "package_unit": "包装单位",
        "units_per_package": "每箱数量",
        "current_quantity": "当前库存",
        "minimum_quantity": "最低库存",
    }).copy()
    for column in ["每箱数量", "当前库存", "最低库存"]:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0.0)
    result["当前库存（箱）"] = result.apply(_to_packages, axis=1)
    result["最低库存（箱）"] = result.apply(
        lambda row: _to_packages(row, quantity_field="最低库存"), axis=1
    )
    return result


def _to_packages(row, quantity_field="当前库存"):
    package_unit = str(row.get("包装单位") or "").strip()
    package_size = pd.to_numeric(row.get("每箱数量"), errors="coerce")
    quantity = pd.to_numeric(row.get(quantity_field), errors="coerce")
    if package_unit != "箱" or pd.isna(package_size) or package_size <= 0:
        return pd.NA
    if pd.isna(quantity):
        return pd.NA
    return round(float(quantity) / float(package_size), 2)


def _stock_plan(row):
    package_unit = str(row.get("包装单位") or "").strip()
    package_size = pd.to_numeric(row.get("每箱数量"), errors="coerce")
    return calculate_stock_plan(
        row.get("库存基准总数"),
        row.get("预测日耗合计"),
        target_days=row.get("目标备货天数"),
        minimum_quantity=row.get("最低库存"),
        package_size=(
            package_size
            if package_unit == "箱" and pd.notna(package_size)
            else None
        ),
    )
