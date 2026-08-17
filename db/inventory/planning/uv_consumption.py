from datetime import date, timedelta

import pandas as pd

from db.batches import filter_active_batch_records
from db.planning import build_daily_usage_contract, empty_daily_usage_contract
from utils.erp.inventory_mapping import KEY_COLUMNS
from utils.daily_usage_model import (
    EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST,
    build_daily_usage_summary,
)


UV_DAILY_ORDERS_SPREADSHEET_ID = (
    "1kbbexU-zePCPw5Rg5R2fJlcbnRLVFPYZQcL5U_Qoy7Y"
)
UV_DAILY_ORDERS_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    f"{UV_DAILY_ORDERS_SPREADSHEET_ID}/edit"
)
UV_GOOGLE_DRIVE_FOLDER_ID = "1MhAq1n1dDd9P5WD0gdrR2uXH0Veb_MzA"
UV_GOOGLE_DRIVE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/"
    f"{UV_GOOGLE_DRIVE_FOLDER_ID}"
)
UV_CONSUMPTION_LOOKBACK_DAYS = 14
UV_GOOGLE_SHEETS_REASON_PREFIX = "Google Sheets UV每日消耗"
UV_CURRENT_MODEL_START_DATES = {
    ("铁板画", "铁牌", "2030"): date(2026, 7, 28),
    ("铁板画", "铝牌", "2030"): date(2026, 7, 28),
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
    model = build_uv_consumption_model(
        pd.DataFrame(rows), current_date, lookback_days
    )
    active = (
        supabase.table("inventory_items")
        .select("category,material,color,size")
        .eq("department", "UV")
        .eq("is_active", True)
        .execute().data or []
    )
    return filter_uv_model_to_active_skus(model, pd.DataFrame(active))


def filter_uv_model_to_active_skus(model_df, active_inventory_df):
    model = pd.DataFrame(model_df).copy()
    active = pd.DataFrame(active_inventory_df).copy()
    if model.empty or active.empty:
        return model.iloc[0:0].copy()
    model_keys = ["品类", "材质", "颜色", "型号"]
    active = active.rename(columns={
        "category": "品类", "material": "材质",
        "color": "颜色", "size": "型号",
    })
    for frame in (model, active):
        for column in model_keys:
            frame[column] = frame[column].fillna("").astype(str).str.strip()
        frame["型号"] = frame["型号"].str.upper()
    active_keys = active[model_keys].drop_duplicates()
    return model.merge(
        active_keys, on=model_keys, how="inner", validate="many_to_one"
    )


def build_uv_consumption_model(
    movement_df, current_date, lookback_days=UV_CONSUMPTION_LOOKBACK_DAYS
):
    columns = [
        "品类", "材质", "颜色", "型号", "每日消耗", "有效数据天数",
        "自然日均消耗", "窗口总消耗", "窗口天数",
    ]
    if movement_df.empty:
        return pd.DataFrame(columns=columns)

    result = movement_df.copy()
    result["reason"] = result["reason"].fillna("").astype(str)
    result = result[
        result["reason"].str.startswith(UV_GOOGLE_SHEETS_REASON_PREFIX)
    ]
    result = filter_active_batch_records(result, id_column="batch_id")
    result["日期"] = pd.to_datetime(
        result["movement_date"], errors="coerce"
    ).dt.date
    result["消耗"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0)
    result = result[result["日期"].notna()]
    if result.empty:
        return pd.DataFrame(columns=columns)

    result["材质"] = result["material"].fillna("").astype(str).str.strip()
    result["品类"] = result["category"].fillna("").astype(str).str.strip()
    result["颜色"] = result["color"].fillna("").astype(str).str.strip()
    result["型号"] = (
        result["size"].fillna("").astype(str).str.strip().str.upper()
    )
    keys = ["品类", "材质", "颜色", "型号"]
    result = result.groupby(
        [*keys, "日期"], as_index=False
    )["消耗"].sum()
    result = result[result["消耗"] < 0]
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
    grouped = build_daily_usage_summary(
        result,
        keys,
        "消耗",
        current_date,
        lookback_days,
        date_column="日期",
        effective_day_mode=EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST,
        observation_dates=sorted(result["日期"].unique()),
        usage_column="每日消耗",
        effective_days_column="有效数据天数",
        natural_usage_column="自然日均消耗",
        total_usage_column="窗口总消耗",
        window_days_column="窗口天数",
        round_digits=1,
    )
    return grouped[columns].sort_values(
        ["品类", "材质", "型号"], kind="stable"
    ).reset_index(drop=True)


def build_uv_forecast_usage(model_df):
    if model_df is None or model_df.empty:
        return empty_daily_usage_contract(KEY_COLUMNS)
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
    return build_daily_usage_contract(
        result,
        key_columns=KEY_COLUMNS,
        daily_usage_column="system_daily_usage",
        effective_days_column="有效数据天数",
        window_days_column="窗口天数",
        total_usage_column="窗口总消耗",
        source_type="google_sheets",
        source_label="Google Sheets UV每日消耗",
    )
