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
from db.planning import (
    build_daily_usage_contract,
    calculate_arrival_plan,
    calculate_stock_plan,
    classify_inventory_plan,
    empty_daily_usage_contract,
)


LOOKBACK_DAYS = 14
LOW_COVERAGE_DAYS = 14


def normalize_forecast_usage(model_df, department, category):
    if model_df is None or model_df.empty:
        return empty_daily_usage_contract(KEY_COLUMNS)
    result = model_df.rename(columns={
        "consumption_quantity": "system_daily_usage",
    }).copy()
    result["department"] = department
    result["category"] = category or ""
    result["planning_material"] = (
        "全部品牌/材质" if department == "DTF" else ""
    )
    return build_daily_usage_contract(
        result,
        key_columns=KEY_COLUMNS,
        daily_usage_column="system_daily_usage",
        source_type="production_model",
        source_label=f"{category}消耗模型",
    )


def build_incoming_inventory_forecast(
    inventory_df, container_df, system_usage_df, outbound_df, today,
    department, target_days=55,
):
    current = normalize_inventory_for_planning(inventory_df, department)
    incoming = normalize_inventory_for_planning(container_df, department)
    current = _sum_quantity(current, "quantity", "current_quantity")
    incoming_plan = _all_incoming(incoming, today)
    system = _normalize_usage(system_usage_df)
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
    result["usage_source_label"] = result.get(
        "usage_source_label", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    result["arrival_events"] = result["arrival_events"].apply(
        lambda value: value if isinstance(value, list) else []
    )
    result["_forecast_today"] = today
    result["days_to_arrival"] = result.apply(
        lambda row: _days_to_arrival(row, today), axis=1
    )
    result["_arrival_plan"] = result.apply(_arrival_plan, axis=1)
    result["coverage_days"] = result.apply(
        lambda row: calculate_stock_plan(
            row["current_quantity"], row["system_daily_usage"]
        ).coverage_days,
        axis=1,
    )
    result["quantity_before_arrival"] = result["_arrival_plan"].map(
        lambda plan: plan.quantity_before_first_arrival
    )
    result["shortage"] = result["_arrival_plan"].map(
        lambda plan: plan.shortage_before_arrivals
    )
    result["quantity_after_arrival"] = result["_arrival_plan"].map(
        lambda plan: plan.quantity_after_all_arrivals
    )
    result["coverage_after_arrival"] = result["_arrival_plan"].map(
        lambda plan: plan.coverage_after_all_arrivals
    )
    result["target_days"] = max(int(target_days or 0), 0)
    result["_stock_plan"] = result.apply(
        lambda row: calculate_stock_plan(
            row["current_quantity"],
            row["system_daily_usage"],
            target_days=row["target_days"],
        ),
        axis=1,
    )
    result["target_quantity"] = result["_stock_plan"].map(
        lambda plan: plan.target_quantity or 0
    )
    result["reorder_quantity"] = result["_stock_plan"].map(
        lambda plan: plan.reorder_quantity
    )
    result["reorder_after_arrivals"] = result.apply(
        lambda row: calculate_stock_plan(
            row["quantity_after_arrival"],
            row["system_daily_usage"],
            target_days=row["target_days"],
        ).reorder_quantity,
        axis=1,
    )
    result["判断"] = result.apply(_forecast_status, axis=1)
    if department == "DTF":
        result["录入核对"] = result.apply(
            lambda row: (
                "不适用" if row.get("category") == "彩色短袖"
                else _audit_status(row)
            ),
            axis=1,
        )
    else:
        result["录入核对"] = "不适用"
    return _format_forecast(result)


def _sum_quantity(df, source, target):
    result = df.copy()
    result[source] = pd.to_numeric(
        result.get(source, 0), errors="coerce"
    ).fillna(0)
    return result.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        **{target: (source, "sum")}
    )


def _normalize_usage(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=[*KEY_COLUMNS, "system_daily_usage"])
    source = df.copy()
    usage_column = (
        "daily_usage" if "daily_usage" in source
        else "system_daily_usage"
    )
    source["usage_source_label"] = source.get(
        "usage_source_label", pd.Series("", index=source.index)
    ).fillna("").astype(str).str.strip()
    return source.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        system_daily_usage=(usage_column, "sum"),
        usage_source_label=(
            "usage_source_label",
            lambda values: "、".join(dict.fromkeys(
                value for value in values if value
            )),
        ),
    )


def _manual_average(df, department):
    if df is None or df.empty:
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


def _arrival_plan(row):
    return calculate_arrival_plan(
        row["current_quantity"],
        row["system_daily_usage"],
        row["arrival_events"],
        row["_forecast_today"],
    )


def _forecast_status(row):
    return classify_inventory_plan(
        has_arrivals=bool(row["arrival_events"]),
        is_arrived=STATE_ARRIVED in row["normalized_status"],
        days_to_arrival=row["days_to_arrival"],
        daily_usage=row["system_daily_usage"],
        coverage_days=row["coverage_days"],
        shortage=row["shortage"],
        coverage_after_arrival=row["coverage_after_arrival"],
        has_overdue_estimate=row.get("has_overdue_estimate", False),
        low_coverage_days=LOW_COVERAGE_DAYS,
    )


def _audit_status(row):
    system, manual = row["system_daily_usage"], row["manual_daily_usage"]
    if system > 0 and manual == 0:
        return "未录入出库"
    if system == 0 and manual > 0:
        return "可能录错规格"
    if system == 0:
        return "无数据"
    return "需核对" if abs(manual - system) / system > 0.3 else "接近"
