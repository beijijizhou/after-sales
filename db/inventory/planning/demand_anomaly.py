from datetime import timedelta

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


DAILY_OUTBOUND_PATTERN = "每日正常出货|每日出货|黑白短袖出库"


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
    return normalize_daily_outbound_history(pd.DataFrame(response.data))


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


def build_demand_anomaly_table(model_df, outbound_df, inventory_df):
    if model_df.empty or outbound_df.empty:
        return pd.DataFrame()

    model = model_df.rename(columns={
        "color": "颜色", "size": "尺码",
        "consumption_quantity": "基础日耗",
    }).copy()
    model["基础日耗"] = pd.to_numeric(model["基础日耗"], errors="coerce").fillna(0)
    model_total = max(float(model["基础日耗"].sum()), 1)
    stock = build_stock_by_sku(inventory_df)
    dates = sorted(outbound_df["日期"].dropna().unique())[-3:]
    totals = outbound_df.groupby("日期")["实际出库"].sum().to_dict()

    rows = []
    for row in model.to_dict("records"):
        color, size = row["颜色"], row["尺码"]
        baseline = max(int(row["基础日耗"]), 0)
        sku = outbound_df[
            (outbound_df["颜色"] == color) & (outbound_df["尺码"] == size)
        ].set_index("日期")["实际出库"].to_dict()
        values = [int(sku.get(date, 0)) for date in dates]
        signals = [
            is_abnormal_day(value, baseline, totals.get(date, 0), baseline / model_total)
            for date, value in zip(dates, values)
        ]
        latest = values[-1] if values else 0
        two_values = values[-2:]
        three_values = values[-3:]
        two_average = round(sum(two_values) / len(two_values)) if two_values else 0
        three_average = round(sum(three_values) / len(three_values)) if three_values else 0
        two_high = len(signals) >= 2 and all(signals[-2:])
        three_high = (
            len(three_values) == 3 and baseline > 0
            and sum(three_values) > baseline * 3 * 1.4
        )
        status = "爆单" if three_high else "持续偏高" if two_high else "观察" if signals and signals[-1] else "正常"
        risk_rate = (
            max(baseline, round(two_average * 0.6 + three_average * 0.4))
            if two_high or three_high else baseline
        )
        current_stock = int(stock.get((color, size), 0))
        latest_total = max(int(totals.get(dates[-1], 0)), 1) if dates else 1
        expected_share = baseline / model_total
        actual_share = latest / latest_total
        share_ratio = actual_share / expected_share if expected_share else 0
        total_ratio = latest_total / model_total
        anomaly_type = "正常"
        if signals and signals[-1]:
            anomaly_type = (
                "整体订单增加" if total_ratio >= 1.3 and share_ratio < 1.3
                else "单品占比上升" if share_ratio >= 1.5
                else "单品消耗上升"
            )
        rows.append({
            "颜色": color, "尺码": size, "当前库存": current_stock,
            "最近出库日期": dates[-1] if dates else None,
            "基础日耗": baseline, "最近出库": latest,
            "近2次平均": two_average, "近3次平均": three_average,
            "消耗倍数": round(latest / baseline, 2) if baseline else None,
            "占比偏离": round(share_ratio, 2) if expected_share else None,
            "异常类型": anomaly_type, "状态": status, "风险日耗": risk_rate,
            "风险剩余天数": round(current_stock / risk_rate) if risk_rate else None,
        })
    return pd.DataFrame(rows)


def is_abnormal_day(actual, baseline, total, expected_share):
    if baseline <= 0:
        return False
    absolute_high = actual >= baseline * 1.5
    actual_share = actual / total if total else 0
    mix_high = actual >= 72 and expected_share > 0 and actual_share >= expected_share * 1.5
    return absolute_high or mix_high


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
