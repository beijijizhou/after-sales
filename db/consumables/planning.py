from datetime import timedelta

import pandas as pd

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
        "最低库存", "安全库存缺口", "建议备货天数", "建议下单量",
        "建议下单量（箱）", "日耗依据", "有效数据天数",
        "自然窗口日均", "窗口天数",
    ]
    model = pd.DataFrame(model_df).copy()
    if model.empty or current_date is None:
        return pd.DataFrame(columns=columns)

    result = model.copy()
    result["库存基准总数"] = pd.to_numeric(
        result["当前库存"], errors="coerce"
    ).fillna(0.0)
    result["预测日耗合计"] = pd.to_numeric(
        result["最近领用日均"], errors="coerce"
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
    result["建议备货天数"] = int(max(coverage_days, 0))
    result["库存基准日期"] = current_date
    result["当前日期"] = current_date
    result["最低剩余天数"] = result.apply(_coverage_days, axis=1)
    result["预计最早耗尽日期"] = result["最低剩余天数"].apply(
        lambda value: (
            current_date + timedelta(days=int(value))
            if pd.notna(value) else pd.NaT
        )
    )
    result["安全库存缺口"] = (
        result["最低库存"] - result["库存基准总数"]
    ).clip(lower=0)
    result["建议下单量"] = result.apply(_recommended_quantity, axis=1)
    result["建议下单量（箱）"] = result.apply(_recommended_packages, axis=1)
    result["日耗依据"] = result.apply(
        lambda row: (
            f"最近{int(row.get('窗口天数') or CONSUMABLE_LOOKBACK_DAYS)}天领用"
            if float(row["预测日耗合计"]) > 0
            else "暂无有效领用"
        ),
        axis=1,
    )
    result = result.sort_values(
        ["建议下单量", "最低剩余天数", "分类", "耗材名称", "规格/型号"],
        ascending=[False, True, True, True, True],
        kind="stable",
        na_position="last",
    )
    return result[columns].reset_index(drop=True)


def _active_issue_movements(batches_df, movements_df):
    batches = pd.DataFrame(batches_df).copy()
    movements = pd.DataFrame(movements_df).copy()
    columns = ["item_id", "movement_date", "issue_quantity"]
    if batches.empty or movements.empty:
        return pd.DataFrame(columns=columns)

    reversed_batch_ids = set(
        batches["reversal_of_batch_id"].dropna().astype(str)
    )
    active_batches = batches[
        batches["reversal_of_batch_id"].isna()
        & ~batches["id"].astype(str).isin(reversed_batch_ids)
        & (batches["movement_type"] == "issue")
    ].copy()
    if active_batches.empty:
        return pd.DataFrame(columns=columns)

    reversed_movement_ids = set(
        movements["reversal_of_movement_id"].dropna().astype(str)
    )
    active_movements = movements[
        movements["reversal_of_movement_id"].isna()
        & ~movements["id"].astype(str).isin(reversed_movement_ids)
    ].copy()
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


def _coverage_days(row):
    daily_usage = float(row.get("预测日耗合计") or 0)
    current_quantity = float(row.get("库存基准总数") or 0)
    if daily_usage <= 0:
        return pd.NA
    return int(current_quantity / daily_usage)


def _recommended_quantity(row):
    daily_usage = float(row.get("预测日耗合计") or 0)
    current_quantity = float(row.get("库存基准总数") or 0)
    minimum_quantity = float(row.get("最低库存") or 0)
    target_days = int(row.get("建议备货天数") or 0)
    target_quantity = max(daily_usage * target_days, minimum_quantity)
    return max(round(target_quantity - current_quantity), 0)


def _recommended_packages(row):
    recommended = float(row.get("建议下单量") or 0)
    package_unit = str(row.get("包装单位") or "").strip()
    package_size = pd.to_numeric(row.get("每箱数量"), errors="coerce")
    if recommended <= 0:
        return 0
    if package_unit != "箱" or pd.isna(package_size) or package_size <= 0:
        return pd.NA
    return round(recommended / float(package_size), 2)
