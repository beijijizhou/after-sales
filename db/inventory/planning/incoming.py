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
    incoming_plan = _all_incoming(incoming)
    system = _normalize_usage(system_usage_df, "system_daily_usage")
    manual = (
        _manual_average(outbound_df, department)
        if department == "DTF"
        else pd.DataFrame(columns=[*KEY_COLUMNS, "manual_daily_usage"])
    )

    result = incoming_plan.merge(current, on=KEY_COLUMNS, how="left")
    result = result.merge(system, on=KEY_COLUMNS, how="left")
    result = result.merge(manual, on=KEY_COLUMNS, how="left")
    numeric = [
        "current_quantity", "system_daily_usage", "manual_daily_usage",
    ]
    for column in numeric:
        result[column] = result[column].fillna(0)
    result["_forecast_today"] = today
    result["days_to_arrival"] = result.apply(
        lambda row: _days_to_arrival(row, today), axis=1
    )
    result["coverage_days"] = result.apply(_coverage_days, axis=1)
    result["quantity_before_arrival"] = result.apply(
        _quantity_before_arrival, axis=1
    )
    result["shortage"] = result.apply(_projected_shortage, axis=1)
    result["quantity_after_arrival"] = result.apply(
        _quantity_after_all_arrivals, axis=1
    )
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


def build_incoming_executive_view(forecast):
    columns = [
        "SKU", "判断", "当前库存", "日耗", "可撑天数", "全部在途货柜",
        "到货安排", "在途总量", "到货前缺口", "到货后可撑",
    ]
    if forecast is None or forecast.empty:
        return pd.DataFrame(columns=columns)
    result = forecast.copy()
    result["SKU"] = result.apply(
        lambda row: "｜".join(
            value for value in [
                _display_text(row.get("品类")),
                _display_text(row.get("材质口径")),
                _display_text(row.get("颜色")),
                _display_text(row.get("规格")),
            ]
            if value
        ),
        axis=1,
    )
    result = result.rename(columns={
        "系统日均": "日耗",
        "当前可撑天数": "可撑天数",
        "到货后可撑天数": "到货后可撑",
    })
    return result[columns]


def _all_incoming(df):
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
    rows = []
    for identity, group in result.groupby(KEY_COLUMNS, dropna=False):
        schedule_rows = (
            group.groupby(
                [
                    "forecast_arrival_date", "container_no",
                    "normalized_status",
                ],
                dropna=False,
                as_index=False,
            )["quantity"].sum()
            .sort_values(["forecast_arrival_date", "container_no"])
        )
        events = [
            (row["forecast_arrival_date"], float(row["quantity"]))
            for row in schedule_rows.to_dict("records")
        ]
        schedule = "｜".join(
            f"{row['forecast_arrival_date']:%m/%d} "
            f"{row['container_no']} {int(row['quantity']):,}"
            for row in schedule_rows.to_dict("records")
        )
        rows.append({
            **dict(zip(KEY_COLUMNS, identity)),
            "first_arrival_date": schedule_rows[
                "forecast_arrival_date"
            ].min(),
            "last_arrival_date": schedule_rows[
                "forecast_arrival_date"
            ].max(),
            "incoming_quantity": float(schedule_rows["quantity"].sum()),
            "container_no": _join_unique(schedule_rows["container_no"]),
            "normalized_status": _join_unique(
                schedule_rows["normalized_status"]
            ),
            "arrival_schedule": schedule,
            "arrival_events": events,
        })
    return pd.DataFrame(rows)


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
        "container_no": "全部在途货柜",
        "arrival_schedule": "到货安排",
        "first_arrival_date": "最早到货",
        "last_arrival_date": "最晚到货",
        "days_to_arrival": "距到货天数",
        "incoming_quantity": "在途总量",
        "quantity_before_arrival": "到货前预计剩余",
        "quantity_after_arrival": "到货后预计库存",
        "coverage_after_arrival": "到货后可撑天数",
        "normalized_status": "货柜状态",
        "shortage": "到货前缺口",
    })
    columns = [
        "品类", "材质口径", "颜色", "规格", "判断", "当前库存",
        "系统日均", "当前可撑天数", "全部在途货柜", "货柜状态",
        "到货安排", "最早到货", "最晚到货", "距到货天数",
        "到货前预计剩余", "到货前缺口", "在途总量", "到货后预计库存",
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
    return (row["first_arrival_date"] - today).days


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
    if row["system_daily_usage"] <= 0:
        return 0
    shortage = 0
    today = row["_forecast_today"]
    arrival_dates = sorted({
        arrival_date for arrival_date, _quantity in row["arrival_events"]
    })
    for arrival_date in arrival_dates:
        days = max((arrival_date - today).days, 0)
        stock_before = (
            float(row["current_quantity"])
            - float(row["system_daily_usage"]) * days
            + sum(
                previous_quantity
                for previous_date, previous_quantity in row["arrival_events"]
                if previous_date < arrival_date
            )
        )
        shortage = max(shortage, math.ceil(max(-stock_before, 0)))
    return shortage


def _quantity_after_all_arrivals(row):
    if not row["arrival_events"]:
        return max(float(row["current_quantity"]), 0)
    last_date = max(date for date, _quantity in row["arrival_events"])
    days = max((last_date - row["_forecast_today"]).days, 0)
    return max(
        float(row["current_quantity"])
        - float(row["system_daily_usage"]) * days
        + sum(quantity for _date, quantity in row["arrival_events"]),
        0,
    )


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


def _display_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in {"", "未填写"} else text
