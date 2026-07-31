import math

import pandas as pd

from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    normalize_container_state,
)
from utils.erp.inventory_mapping import (
    KEY_COLUMNS,
    normalize_inventory_for_planning,
)


LOOKBACK_DAYS = 14
LOW_COVERAGE_DAYS = 14


def normalize_forecast_usage(model_df, department, category):
    if model_df is None or model_df.empty:
        return pd.DataFrame()
    result = model_df.rename(columns={
        "consumption_quantity": "system_daily_usage",
    }).copy()
    result["department"] = department
    result["category"] = category or ""
    result["planning_material"] = (
        "全部品牌/材质" if department == "DTF" else ""
    )
    return result[[
        *KEY_COLUMNS, "system_daily_usage",
    ]]


def build_incoming_inventory_forecast(
    inventory_df, container_df, system_usage_df, outbound_df, today,
    department,
):
    if container_df.empty:
        return pd.DataFrame()
    current = normalize_inventory_for_planning(inventory_df, department)
    incoming = normalize_inventory_for_planning(container_df, department)
    current = _sum_quantity(current, "quantity", "current_quantity")
    nearest = _nearest_incoming(incoming)
    system = _normalize_usage(system_usage_df, "system_daily_usage")
    manual = (
        _manual_average(outbound_df, department)
        if department == "DTF"
        else pd.DataFrame(columns=[*KEY_COLUMNS, "manual_daily_usage"])
    )

    result = nearest.merge(current, on=KEY_COLUMNS, how="left")
    result = result.merge(system, on=KEY_COLUMNS, how="left")
    result = result.merge(manual, on=KEY_COLUMNS, how="left")
    numeric = [
        "current_quantity", "system_daily_usage", "manual_daily_usage",
    ]
    for column in numeric:
        result[column] = result[column].fillna(0)
    result["days_to_arrival"] = result.apply(
        lambda row: _days_to_arrival(row, today), axis=1
    )
    result["coverage_days"] = result.apply(_coverage_days, axis=1)
    result["quantity_before_arrival"] = result.apply(
        _quantity_before_arrival, axis=1
    )
    result["shortage"] = result.apply(_projected_shortage, axis=1)
    result["quantity_after_arrival"] = (
        result["current_quantity"]
        - result["system_daily_usage"]
        * result["days_to_arrival"].clip(lower=0)
        + result["incoming_quantity"]
    ).clip(lower=0)
    result["coverage_after_arrival"] = result.apply(
        _coverage_after_arrival, axis=1
    )
    result["判断"] = result.apply(_forecast_status, axis=1)
    result["录入核对"] = (
        result.apply(_audit_status, axis=1)
        if department == "DTF"
        else "不适用"
    )
    return _format_forecast(result)


def build_inventory_audit_issues(forecast):
    columns = [
        "品类", "材质口径", "颜色", "规格", "问题",
        "系统日均", "仓库申报日均", "日均差额", "差异比例", "核对建议",
    ]
    if forecast is None or forecast.empty:
        return pd.DataFrame(columns=columns)
    issues = forecast[
        ~forecast["录入核对"].isin(["接近", "无数据", "不适用"])
    ].copy()
    if issues.empty:
        return pd.DataFrame(columns=columns)
    issues["问题"] = issues["录入核对"]
    issues["日均差额"] = (
        issues["仓库申报日均"] - issues["系统日均"]
    ).round(1)
    issues["差异比例"] = issues.apply(
        lambda row: (
            abs(row["日均差额"]) / row["系统日均"] * 100
            if row["系统日均"] > 0 else None
        ),
        axis=1,
    )
    issues["核对建议"] = issues.apply(_audit_suggestion, axis=1)
    return issues[columns].sort_values(
        ["问题", "差异比例"], ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)


def _nearest_incoming(df):
    result = df.copy()
    result["quantity"] = pd.to_numeric(
        result["quantity"], errors="coerce"
    ).fillna(0)
    for column in ["expected_arrival_date", "actual_arrival_date"]:
        result[column] = pd.to_datetime(
            result.get(column), errors="coerce"
        ).dt.date
    result["normalized_status"] = result.get(
        "status", ""
    ).map(normalize_container_state)
    arrived = result["normalized_status"] == STATE_ARRIVED
    result["forecast_arrival_date"] = result[
        "expected_arrival_date"
    ]
    result.loc[arrived, "forecast_arrival_date"] = result.loc[
        arrived
    ].apply(
        lambda row: (
            row["actual_arrival_date"]
            if pd.notna(row["actual_arrival_date"])
            else row["expected_arrival_date"]
        ),
        axis=1,
    )
    result = result.dropna(subset=["forecast_arrival_date"])
    result["container_no"] = result["container_no"].fillna(
        result["container_key"]
    ).astype(str)
    nearest_date = result.groupby(KEY_COLUMNS, dropna=False)[
        "forecast_arrival_date"
    ].transform("min")
    result = result[result["forecast_arrival_date"] == nearest_date]
    return result.groupby(
        [*KEY_COLUMNS, "forecast_arrival_date"],
        dropna=False,
        as_index=False,
    ).agg(
        incoming_quantity=("quantity", "sum"),
        container_no=("container_no", _join_unique),
        normalized_status=("normalized_status", _join_unique),
    )


def _format_forecast(result):
    result = result.rename(columns={
        "category": "品类",
        "planning_material": "材质口径",
        "color": "颜色",
        "size": "规格",
        "current_quantity": "当前库存",
        "system_daily_usage": "系统日均",
        "manual_daily_usage": "仓库申报日均",
        "coverage_days": "当前可撑天数",
        "container_no": "最近货柜",
        "forecast_arrival_date": "预计/实际到货",
        "days_to_arrival": "距到货天数",
        "incoming_quantity": "货柜数量",
        "quantity_before_arrival": "到货前预计剩余",
        "quantity_after_arrival": "到货后预计库存",
        "coverage_after_arrival": "到货后可撑天数",
        "normalized_status": "货柜状态",
        "shortage": "到货前缺口",
    })
    columns = [
        "品类", "材质口径", "颜色", "规格", "判断", "当前库存",
        "系统日均", "当前可撑天数", "最近货柜", "货柜状态",
        "预计/实际到货", "距到货天数", "到货前预计剩余",
        "到货前缺口", "货柜数量", "到货后预计库存",
        "到货后可撑天数", "仓库申报日均", "录入核对",
    ]
    return result[columns].sort_values(
        ["到货前缺口", "到货后可撑天数"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _sum_quantity(df, source, target):
    result = df.copy()
    result[source] = pd.to_numeric(
        result.get(source, 0), errors="coerce"
    ).fillna(0)
    return result.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        **{target: (source, "sum")}
    )


def _normalize_usage(df, column):
    if df.empty:
        return pd.DataFrame(columns=[*KEY_COLUMNS, column])
    return df.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        **{column: (column, "sum")}
    )


def _manual_average(df, department):
    if df.empty:
        return pd.DataFrame(
            columns=[*KEY_COLUMNS, "manual_daily_usage"]
        )
    result = normalize_inventory_for_planning(df, department)
    result["manual"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0).abs()
    return result.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        manual_daily_usage=(
            "manual", lambda values: values.sum() / LOOKBACK_DAYS
        )
    )


def _days_to_arrival(row, today):
    if STATE_ARRIVED in row["normalized_status"]:
        return 0
    return (row["forecast_arrival_date"] - today).days


def _coverage_days(row):
    if row["system_daily_usage"] <= 0:
        return None
    return row["current_quantity"] / row["system_daily_usage"]


def _quantity_before_arrival(row):
    days = max(row["days_to_arrival"], 0)
    return max(math.floor(
        row["current_quantity"] - row["system_daily_usage"] * days
    ), 0)


def _projected_shortage(row):
    if row["days_to_arrival"] < 0 or row["system_daily_usage"] <= 0:
        return 0
    return max(math.ceil(
        row["system_daily_usage"] * row["days_to_arrival"]
        - row["current_quantity"]
    ), 0)


def _coverage_after_arrival(row):
    if row["system_daily_usage"] <= 0:
        return None
    return row["quantity_after_arrival"] / row["system_daily_usage"]


def _forecast_status(row):
    if STATE_ARRIVED in row["normalized_status"]:
        return "已到柜待入库"
    if row["days_to_arrival"] < 0:
        return "货柜已延迟"
    if row["system_daily_usage"] <= 0:
        return "暂无系统消耗依据"
    if row["shortage"] > 0:
        return "到货前可能断货"
    if row["coverage_after_arrival"] < LOW_COVERAGE_DAYS:
        return "到货后库存仍偏低"
    return "可撑到到货"


def _audit_status(row):
    system, manual = row["system_daily_usage"], row["manual_daily_usage"]
    if system > 0 and manual == 0:
        return "未录入出库"
    if system == 0 and manual > 0:
        return "可能录错规格"
    if system == 0:
        return "无数据"
    return "需核对" if abs(manual - system) / system > 0.3 else "接近"


def _audit_suggestion(row):
    if row["录入核对"] == "未录入出库":
        return "系统有生产但仓库无匹配出库；检查漏录或颜色/规格映射"
    if row["录入核对"] == "可能录错规格":
        return "仓库有出库但系统无相同 SKU；检查材质、颜色和规格"
    direction = "高于" if row["日均差额"] > 0 else "低于"
    return (
        f"仓库申报{direction}系统生产 "
        f"{abs(row['日均差额']):.1f}/天"
    )


def _join_unique(values):
    return " / ".join(sorted({
        str(value).strip() for value in values if str(value).strip()
    }))
