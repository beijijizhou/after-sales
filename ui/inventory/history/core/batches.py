import pandas as pd

from ui.inventory.history.core.tables import format_date_columns
from utils.daily_consumption import (
    UV_REASON_PREFIX,
    daily_consumption_business_type,
)
from utils.inventory_movements import is_stocktake_reason, movement_business_type


NY_TIMEZONE = "America/New_York"


def _to_new_york_timestamp(values):
    return pd.to_datetime(values, errors="coerce", utc=True).dt.tz_convert(
        NY_TIMEZONE
    )


def _summarize_categories(values):
    categories = {
        str(value).strip() for value in values if str(value).strip()
    }
    if len(categories) == 1:
        return next(iter(categories))
    return "多品类"


def add_movement_batch_key(movement_df):
    movement_df = format_date_columns(movement_df, ["movement_date"]).copy()
    movement_df["quantity_change"] = pd.to_numeric(
        movement_df["quantity_change"], errors="coerce"
    ).fillna(0).astype(int)
    movement_df["reason"] = movement_df.get("reason", "").fillna("").astype(str)
    if "created_by" not in movement_df.columns:
        movement_df["created_by"] = "a"
    movement_df["created_by"] = movement_df["created_by"].fillna("a").astype(str)
    if "reversal_of_batch_id" not in movement_df.columns:
        movement_df["reversal_of_batch_id"] = None
    movement_df["recorded_at"] = _to_new_york_timestamp(
        movement_df["created_at"]
    )
    movement_df["recorded_key"] = movement_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
    movement_df["direction"] = movement_df["quantity_change"].apply(lambda value: "入库" if value > 0 else "出库")
    stocktake = movement_df["reason"].map(is_stocktake_reason)
    movement_df.loc[stocktake, "direction"] = "库存设置"
    movement_df["batch_key"] = (
        "movement|"
        + movement_df["recorded_key"].fillna("")
        + "|"
        + movement_df["movement_date"].astype(str)
        + "|"
        + movement_df["department"].fillna("").astype(str)
        + "|"
        + movement_df["category"].fillna("").astype(str)
        + "|"
        + movement_df["direction"]
        + "|"
        + movement_df["reason"]
    )
    if "batch_id" in movement_df.columns:
        batch_ids = movement_df["batch_id"].fillna("").astype(str).str.strip()
        movement_df["batch_key"] = movement_df["batch_key"].where(
            batch_ids == "", "movement|" + batch_ids
        )
    uv_daily = (
        movement_df["department"].fillna("").astype(str).eq("UV")
        & movement_df["reason"].str.startswith(UV_REASON_PREFIX)
        & movement_df["quantity_change"].lt(0)
    )
    movement_df.loc[uv_daily, "batch_key"] = (
        "daily|UV|"
        + movement_df.loc[uv_daily, "movement_date"].astype(str)
        + "|google-sheets"
    )
    return movement_df


def add_sku_batch_key(sku_import_df):
    sku_import_df = format_date_columns(sku_import_df, ["import_date"]).copy()
    sku_import_df["initial_quantity"] = pd.to_numeric(
        sku_import_df["initial_quantity"], errors="coerce"
    ).fillna(0).astype(int)
    sku_import_df["recorded_at"] = _to_new_york_timestamp(
        sku_import_df["created_at"]
    )
    sku_import_df["recorded_key"] = sku_import_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
    sku_import_df["batch_key"] = (
        "sku|"
        + sku_import_df["recorded_key"].fillna("")
        + "|"
        + sku_import_df["import_date"].astype(str)
        + "|"
        + sku_import_df["department"].fillna("").astype(str)
        + "|"
        + sku_import_df["category"].fillna("").astype(str)
    )
    return sku_import_df


def build_movement_batch_rows(movement_df):
    if movement_df.empty:
        return []

    movement_df = add_movement_batch_key(movement_df)
    reversed_batch_ids = set(
        movement_df["reversal_of_batch_id"].dropna().astype(str)
    )
    grouped_df = (
        movement_df
        .groupby("batch_key", as_index=False)
        .agg(
            recorded_key=("recorded_key", "first"),
            movement_date=("movement_date", "first"),
            department=("department", "first"),
            category=("category", _summarize_categories),
            direction=("direction", "first"),
            reason=("reason", lambda values: "；".join(dict.fromkeys(
                value for value in values if value
            ))),
            created_by=("created_by", "first"),
            batch_id=("batch_id", "first") if "batch_id" in movement_df.columns else ("batch_key", "first"),
            is_reversal=("reversal_of_batch_id", lambda values: values.notna().any()),
            quantity=("quantity_change", lambda values: int(values.abs().sum())),
            sku_count=("reason", "size"),
        )
    )
    uv_daily = grouped_df["reason"].str.startswith(UV_REASON_PREFIX)
    grouped_df.loc[uv_daily, "reason"] = grouped_df.loc[uv_daily].apply(
        lambda row: (
            f"{UV_REASON_PREFIX}｜{row['movement_date']}｜"
            f"{int(row['sku_count'])} 个 SKU"
        ),
        axis=1,
    )
    return [
        {
            "batch_key": row["batch_key"],
            "类型": (
                f"撤销{row['direction']}" if row["is_reversal"]
                else f"已撤销{row['direction']}" if str(row["batch_id"]) in reversed_batch_ids
                else row["direction"]
            ),
            "记录类别": (
                "撤销记录"
                if row["is_reversal"] or str(row["batch_id"]) in reversed_batch_ids
                else "库存表格记录"
            ),
            "记录时间": row["recorded_key"],
            "表格日期": row["movement_date"],
            "部门": row["department"],
            "品类": row["category"],
            "数量": row["quantity"],
            "操作人": row["created_by"],
            "消耗来源": (
                movement_business_type(row["reason"])
                or daily_consumption_business_type(row["reason"])
            ),
            "备注": row["reason"],
        }
        for row in grouped_df.to_dict("records")
    ]


def build_sku_batch_rows(sku_import_df):
    if sku_import_df.empty:
        return []

    sku_import_df = add_sku_batch_key(sku_import_df)
    grouped_df = (
        sku_import_df
        .groupby(["batch_key", "recorded_key", "import_date", "department", "category"], as_index=False)
        .agg(
            quantity=("initial_quantity", "sum"),
        )
    )
    return [
        {
            "batch_key": row["batch_key"],
            "类型": "新增 SKU",
            "记录类别": "库存表格记录",
            "记录时间": row["recorded_key"],
            "表格日期": row["import_date"],
            "部门": row["department"],
            "品类": row["category"],
            "数量": int(row["quantity"]),
            "操作人": "Andy",
            "消耗来源": "",
            "备注": "",
        }
        for row in grouped_df.to_dict("records")
    ]


def build_movement_batches(movement_df, sku_import_df):
    batch_rows = build_movement_batch_rows(movement_df) + build_sku_batch_rows(sku_import_df)
    if not batch_rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(batch_rows)
        .sort_values(["记录时间", "表格日期"], ascending=[False, False])
        .reset_index(drop=True)
    )

