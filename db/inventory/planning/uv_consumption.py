from datetime import date, timedelta

import pandas as pd


UV_DAILY_ORDERS_SPREADSHEET_ID = (
    "1kbbexU-zePCPw5Rg5R2fJlcbnRLVFPYZQcL5U_Qoy7Y"
)
UV_DAILY_ORDERS_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    f"{UV_DAILY_ORDERS_SPREADSHEET_ID}/edit"
)
UV_CONSUMPTION_LOOKBACK_DAYS = 14
UV_GOOGLE_SHEETS_REASON_PREFIX = "Google Sheets UV每日消耗"
UV_CURRENT_MODEL_START_DATES = {
    ("铁板画", "铁牌", "2030"): date(2026, 7, 29),
    ("铁板画", "铝牌", "2030"): date(2026, 7, 29),
}


def load_uv_consumption_history(
    supabase, current_date, lookback_days=UV_CONSUMPTION_LOOKBACK_DAYS
):
    start_date = current_date - timedelta(days=lookback_days - 1)
    rows = (
        supabase.table("inventory_movements")
        .select(
            "category,material,color,size,quantity_change,movement_date,reason,"
            "batch_id,reversal_of_batch_id"
        )
        .eq("department", "UV")
        .gte("movement_date", start_date.isoformat())
        .lte("movement_date", current_date.isoformat())
        .order("movement_date")
        .limit(5000)
        .execute()
        .data
        or []
    )
    return build_uv_consumption_model(
        pd.DataFrame(rows), current_date, lookback_days
    )


def build_uv_consumption_model(
    movement_df, current_date, lookback_days=UV_CONSUMPTION_LOOKBACK_DAYS
):
    columns = [
        "品类", "材质", "颜色", "型号", "每日消耗", "有效数据天数",
    ]
    if movement_df.empty:
        return pd.DataFrame(columns=columns)

    result = movement_df.copy()
    result["reason"] = result["reason"].fillna("").astype(str)
    result = result[
        result["reason"].str.startswith(UV_GOOGLE_SHEETS_REASON_PREFIX)
    ]
    reversed_ids = set(
        result.get("reversal_of_batch_id", pd.Series(dtype=str))
        .dropna().astype(str)
    )
    if "reversal_of_batch_id" in result.columns:
        result = result[result["reversal_of_batch_id"].isna()]
    if "batch_id" in result.columns and reversed_ids:
        result = result[
            ~result["batch_id"].astype(str).isin(reversed_ids)
        ]
    result["日期"] = pd.to_datetime(
        result["movement_date"], errors="coerce"
    ).dt.date
    result["消耗"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0)
    result = result[(result["消耗"] < 0) & result["日期"].notna()]
    if result.empty:
        return pd.DataFrame(columns=columns)

    result["材质"] = result["material"].fillna("").astype(str).str.strip()
    result["品类"] = result["category"].fillna("").astype(str).str.strip()
    result["颜色"] = result["color"].fillna("").astype(str).str.strip()
    result["型号"] = (
        result["size"].fillna("").astype(str).str.strip().str.upper()
    )
    for (category, material, model), start_date in (
        UV_CURRENT_MODEL_START_DATES.items()
    ):
        identity = (
            (result["品类"] == category)
            & (result["材质"] == material)
            & (result["型号"] == model)
        )
        result = result[~identity | (result["日期"] >= start_date)]
    if result.empty:
        return pd.DataFrame(columns=columns)
    result["消耗"] = result["消耗"].abs()
    available_dates = sorted(result["日期"].unique())
    keys = ["品类", "材质", "颜色", "型号"]
    grouped = result.groupby(
        keys, as_index=False
    ).agg(
        period_usage=("消耗", "sum"),
        first_usage_date=("日期", "min"),
    )
    grouped["有效数据天数"] = grouped["first_usage_date"].apply(
        lambda first_date: sum(
            movement_date >= first_date
            for movement_date in available_dates
        )
    )
    grouped["每日消耗"] = (
        grouped["period_usage"] / grouped["有效数据天数"]
    ).round(1)
    return grouped[columns].sort_values(
        ["品类", "材质", "型号"], kind="stable"
    ).reset_index(drop=True)


def build_uv_forecast_usage(model_df):
    columns = [
        "department", "category", "planning_material", "color", "size",
        "system_daily_usage",
    ]
    if model_df is None or model_df.empty:
        return pd.DataFrame(columns=columns)
    result = model_df.rename(columns={
        "品类": "category",
        "材质": "planning_material",
        "颜色": "color",
        "型号": "size",
        "每日消耗": "system_daily_usage",
    }).copy()
    result["department"] = "UV"
    result["category"] = result["category"].fillna("").astype(str).str.strip()
    result["planning_material"] = (
        result["planning_material"].fillna("").astype(str).str.strip()
    )
    result["color"] = result["color"].fillna("").astype(str).str.strip()
    result["size"] = (
        result["size"].fillna("").astype(str).str.strip().str.upper()
    )
    result["system_daily_usage"] = pd.to_numeric(
        result["system_daily_usage"], errors="coerce"
    ).fillna(0)
    return result[columns]


def build_uv_container_coverage(model_df, inventory_df, container_df):
    columns = [
        "品类", "材质", "颜色", "型号", "每日消耗", "当前库存",
        "当前可撑天数", "最近货柜", "预计到货日期", "货柜数量",
        "到货后可撑天数",
    ]
    if model_df.empty:
        return pd.DataFrame(columns=columns)
    keys = ["品类", "材质", "颜色", "型号"]
    current = _normalize_stock_rows(inventory_df)
    incoming = _normalize_container_rows(container_df)
    result = model_df.merge(current, on=keys, how="left")
    result = result.merge(incoming, on=keys, how="left")
    result["当前库存"] = result["当前库存"].fillna(0).astype(int)
    result["货柜数量"] = result["货柜数量"].fillna(0).astype(int)
    result["最近货柜"] = result["最近货柜"].fillna("无在途货柜")
    result["当前可撑天数"] = (
        result["当前库存"] / result["每日消耗"]
    ).round(1)
    result["到货后可撑天数"] = (
        (result["当前库存"] + result["货柜数量"])
        / result["每日消耗"]
    ).round(1)
    return result[columns]


def _normalize_stock_rows(df):
    columns = ["品类", "材质", "颜色", "型号", "当前库存"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    result = df.rename(columns={
        "category": "品类", "material": "材质", "color": "颜色",
        "size": "型号", "quantity": "当前库存",
    }).copy()
    result["型号"] = result["型号"].fillna("").astype(str).str.upper()
    result["当前库存"] = pd.to_numeric(
        result["当前库存"], errors="coerce"
    ).fillna(0)
    return result.groupby(columns[:-1], as_index=False)["当前库存"].sum()


def _normalize_container_rows(df):
    columns = [
        "品类", "材质", "颜色", "型号", "最近货柜",
        "预计到货日期", "货柜数量",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    result = df.rename(columns={
        "category": "品类", "material": "材质", "color": "颜色",
        "size": "型号", "container_no": "最近货柜",
        "expected_arrival_date": "预计到货日期",
        "quantity": "货柜数量",
    }).copy()
    result["型号"] = result["型号"].fillna("").astype(str).str.upper()
    result["预计到货日期"] = pd.to_datetime(
        result["预计到货日期"], errors="coerce"
    ).dt.date
    result["货柜数量"] = pd.to_numeric(
        result["货柜数量"], errors="coerce"
    ).fillna(0)
    result = result.dropna(subset=["预计到货日期"])
    nearest = result.groupby(
        ["品类", "材质", "颜色", "型号"], dropna=False
    )["预计到货日期"].transform("min")
    result = result[result["预计到货日期"] == nearest]
    return result.groupby(
        ["品类", "材质", "颜色", "型号", "预计到货日期"],
        as_index=False,
    ).agg(
        最近货柜=("最近货柜", lambda values: "、".join(
            sorted({str(value).strip() for value in values if str(value).strip()})
        )),
        货柜数量=("货柜数量", "sum"),
    )
