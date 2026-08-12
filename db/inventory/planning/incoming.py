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
from db.inventory.planning.incoming_containers import all_incoming as _all_incoming
from db.inventory.planning.incoming_views import (
    build_incoming_executive_view,
    build_inventory_audit_issues,
    format_forecast as _format_forecast,
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
    current = normalize_inventory_for_planning(inventory_df, department)
    incoming = normalize_inventory_for_planning(container_df, department)
    current = _sum_quantity(current, "quantity", "current_quantity")
    incoming_plan = _all_incoming(incoming, today)
    system = _normalize_usage(system_usage_df, "system_daily_usage")
    manual = (
        _manual_average(outbound_df, department)
        if department == "DTF"
        else pd.DataFrame(columns=[*KEY_COLUMNS, "manual_daily_usage"])
    )

    base_frames = [
        frame[KEY_COLUMNS]
        for frame in [current, incoming_plan, system, manual]
        if not frame.empty
    ]
    if not base_frames:
        return pd.DataFrame()
    base = pd.concat(base_frames, ignore_index=True).drop_duplicates()
    if base.empty:
        return pd.DataFrame()
    result = base.merge(incoming_plan, on=KEY_COLUMNS, how="left")
    result = result.merge(current, on=KEY_COLUMNS, how="left")
    result = result.merge(system, on=KEY_COLUMNS, how="left")
    result = result.merge(manual, on=KEY_COLUMNS, how="left")
    numeric = [
        "current_quantity", "system_daily_usage", "manual_daily_usage",
    ]
    for column in numeric:
        result[column] = result[column].fillna(0)
    incoming_defaults = {
        "incoming_quantity": 0.0,
        "container_no": "",
        "normalized_status": "",
        "arrival_schedule": "",
        "arrival_overview": "",
        "has_overdue_estimate": False,
    }
    for column, default in incoming_defaults.items():
        result[column] = result[column].fillna(default)
    result["arrival_events"] = result["arrival_events"].apply(
        lambda value: value if isinstance(value, list) else []
    )
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
    if not row["arrival_events"]:
        return None
    if STATE_ARRIVED in row["normalized_status"]:
        return 0
    return (row["first_arrival_date"] - today).days


def _coverage_days(row):
    if row["system_daily_usage"] <= 0:
        return None
    return row["current_quantity"] / row["system_daily_usage"]


def _quantity_before_arrival(row):
    if not row["arrival_events"]:
        return max(math.floor(row["current_quantity"]), 0)
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
    if not row["arrival_events"]:
        if row["system_daily_usage"] <= 0:
            return "暂无系统消耗依据"
        if row["coverage_days"] < LOW_COVERAGE_DAYS:
            return "当前库存偏低"
        return "当前库存可用"
    if STATE_ARRIVED in row["normalized_status"]:
        return "已到柜待入库"
    if row["days_to_arrival"] < 0:
        return "货柜已延迟"
    if row["system_daily_usage"] <= 0:
        return "暂无系统消耗依据"
    if row["shortage"] > 0:
        return "到货前可能断货"
    if row.get("has_overdue_estimate", False):
        return "延期柜按明日估算"
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
