from datetime import timedelta

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.planning.warehouse_usage import (
    build_warehouse_usage_intervals,
)
from db.inventory.operations.daily_outbound_versions import (
    load_daily_outbound_revisions,
)


DAILY_OUTBOUND_PATTERN = "仓库每日出货|每日正常出货|每日出货|黑白短袖出库"


def load_daily_outbound_history(
    supabase, department, category, current_date, lookback_days=28
):
    start_date = current_date - timedelta(days=lookback_days - 1)
    columns = (
        "color,size,quantity_change,movement_date,reason,"
        "batch_id,reversal_of_batch_id"
    )
    response = (
        supabase.table("inventory_movements")
        .select(columns)
        .eq("department", department)
        .eq("category", category)
        .gte("movement_date", start_date.isoformat())
        .lte("movement_date", current_date.isoformat())
        .order("movement_date")
        .limit(5000)
        .execute()
    )
    legacy = normalize_daily_outbound_history(pd.DataFrame(response.data))
    try:
        versioned = _versioned_daily_outbound_history(
            supabase, department, category, start_date, current_date
        )
    except Exception:
        return legacy
    if versioned.empty:
        return legacy
    covered_dates = set(versioned["日期"])
    legacy = legacy[~legacy["日期"].isin(covered_dates)]
    return pd.concat([legacy, versioned], ignore_index=True).sort_values(
        ["日期", "颜色", "尺码"]
    ).reset_index(drop=True)


def _versioned_daily_outbound_history(
    supabase, department, category, start_date, end_date,
):
    batches = load_daily_outbound_revisions(
        supabase, department, category, start_date, end_date
    )
    rows = []
    for batch in batches:
        current_revision = int(batch.get("current_revision") or 0)
        revision = next((
            row for row in batch.get("inventory_daily_outbound_revisions", [])
            if int(row.get("revision_number") or 0) == current_revision
        ), None)
        if revision is None:
            continue
        for line in revision.get("inventory_daily_outbound_lines", []):
            rows.append({
                "日期": pd.to_datetime(batch.get("movement_date")).date(),
                "颜色": str(line.get("color") or "").strip(),
                "尺码": str(line.get("size") or "").strip().upper(),
                "实际出库": int(line.get("requested_quantity") or 0),
            })
    if not rows:
        return pd.DataFrame(columns=["日期", "颜色", "尺码", "实际出库"])
    return (
        pd.DataFrame(rows)
        .groupby(["日期", "颜色", "尺码"], as_index=False)["实际出库"]
        .sum()
    )


def normalize_daily_outbound_history(movement_df):
    if movement_df.empty:
        return pd.DataFrame(columns=["日期", "颜色", "尺码", "实际出库"])

    result = movement_df.copy()
    result["reason"] = result["reason"].fillna("").astype(str)
    result = result[result["reason"].str.contains(DAILY_OUTBOUND_PATTERN, regex=True)]
    reversed_ids = set(result["reversal_of_batch_id"].dropna().astype(str))
    result = result[result["reversal_of_batch_id"].isna()]
    if "batch_id" in result.columns and reversed_ids:
        result = result[~result["batch_id"].astype(str).isin(reversed_ids)]

    result["quantity_change"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0)
    result = result[result["quantity_change"] < 0]
    result["日期"] = pd.to_datetime(result["movement_date"], errors="coerce").dt.date
    result["颜色"] = result["color"].fillna("").astype(str).str.strip()
    result["尺码"] = result["size"].fillna("").astype(str).str.strip().str.upper()
    result["实际出库"] = result["quantity_change"].abs().astype(int)
    return (
        result.dropna(subset=["日期"])
        .groupby(["日期", "颜色", "尺码"], as_index=False)["实际出库"]
        .sum()
    )


def build_demand_anomaly_table(
    model_df, outbound_df, inventory_df, current_date=None
):
    if model_df.empty or outbound_df.empty:
        return pd.DataFrame()

    model = model_df.rename(columns={
        "color": "颜色", "size": "尺码",
        "consumption_quantity": "基础日耗",
    }).copy()
    model["基础日耗"] = pd.to_numeric(model["基础日耗"], errors="coerce").fillna(0)
    stock = build_stock_by_sku(inventory_df)
    intervals = build_warehouse_usage_intervals(
        outbound_df, current_date
    )
    if intervals.empty:
        return pd.DataFrame()

    rows = []
    for row in model.to_dict("records"):
        color, size = row["颜色"], row["尺码"]
        baseline = max(int(row["基础日耗"]), 0)
        sku_intervals = intervals[
            (intervals["颜色"] == color)
            & (intervals["尺码"] == size)
        ].sort_values("本次出库日期")
        if sku_intervals.empty:
            continue
        latest = sku_intervals.iloc[-1]
        latest_average = float(latest["区间日均"])
        previous_average = (
            float(sku_intervals.iloc[-2]["区间日均"])
            if len(sku_intervals) >= 2 else None
        )
        latest_high = baseline > 0 and latest_average >= baseline * 1.5
        previous_high = (
            baseline > 0
            and previous_average is not None
            and previous_average >= baseline * 1.5
        )
        status = (
            "爆单"
            if baseline > 0 and latest_average >= baseline * 2.5
            else "持续偏高"
            if latest_high and previous_high
            else "观察"
            if latest_high
            else "正常"
        )
        risk_rate = (
            max(
                baseline,
                round(
                    latest_average
                    if previous_average is None
                    else latest_average * 0.7 + previous_average * 0.3
                ),
            )
            if status != "正常" else baseline
        )
        current_stock = int(stock.get((color, size), 0))
        usage_ratio = latest_average / baseline if baseline else None
        rows.append({
            "颜色": color, "尺码": size, "当前库存": current_stock,
            "上次出库日期": latest["上次出库日期"],
            "本次出库日期": latest["本次出库日期"],
            "出库间隔天数": int(latest["出库间隔天数"]),
            "本次出库数量": int(latest["本次出库数量"]),
            "区间日均": round(latest_average),
            "上一区间日均": (
                round(previous_average)
                if previous_average is not None else None
            ),
            "基础日耗": baseline,
            "消耗倍数": round(usage_ratio, 2) if usage_ratio else None,
            "异常类型": "区间消耗偏高" if latest_high else "正常",
            "状态": status, "风险日耗": risk_rate,
            "风险剩余天数": round(current_stock / risk_rate) if risk_rate else None,
        })
    return pd.DataFrame(rows)


def build_stock_by_sku(inventory_df):
    rows = []
    for row in inventory_df.to_dict("records"):
        for size in SIZE_COLUMNS:
            rows.append((row.get("颜色", ""), size, int(row.get(size, 0) or 0)))
    return {
        (color, size): int(group["quantity"].sum())
        for (color, size), group in pd.DataFrame(
            rows, columns=["color", "size", "quantity"]
        ).groupby(["color", "size"])
    }


def build_two_week_size_comparison(model_df, outbound_df, current_date):
    columns = [
        "尺码", "模型日耗", "近14天总出库", "近14天实际日均",
        "日均差额", "差异率", "有效出库天数",
    ]
    if model_df.empty or outbound_df.empty:
        return pd.DataFrame(columns=columns)

    start_date = current_date - timedelta(days=13)
    recent = outbound_df[outbound_df["日期"] >= start_date].copy()
    active_dates = sorted(recent["日期"].dropna().unique())
    if not active_dates:
        return pd.DataFrame(columns=columns)

    actual = (
        recent.groupby("尺码")["实际出库"].sum()
        .reindex(SIZE_COLUMNS, fill_value=0)
    )
    model = (
        model_df.assign(
            consumption_quantity=pd.to_numeric(
                model_df["consumption_quantity"], errors="coerce"
            ).fillna(0)
        )
        .groupby("size")["consumption_quantity"].sum()
        .reindex(SIZE_COLUMNS, fill_value=0)
    )
    rows = []
    for size in SIZE_COLUMNS:
        model_daily = int(model[size])
        total = int(actual[size])
        average = round(total / len(active_dates))
        difference = average - model_daily
        rows.append({
            "尺码": size, "模型日耗": model_daily,
            "近14天总出库": total, "近14天实际日均": average,
            "日均差额": difference,
            "差异率": round(difference / model_daily, 2) if model_daily else None,
            "有效出库天数": len(active_dates),
        })
    return pd.DataFrame(rows, columns=columns)


def apply_risk_consumption(model_df, anomaly_df):
    if model_df.empty or anomaly_df.empty:
        return model_df.copy()
    rates = anomaly_df.set_index(["颜色", "尺码"])["风险日耗"].to_dict()
    result = model_df.copy()
    result["consumption_quantity"] = result.apply(
        lambda row: int(rates.get(
            (row.get("color"), row.get("size")), row.get("consumption_quantity", 0)
        )),
        axis=1,
    )
    return result
