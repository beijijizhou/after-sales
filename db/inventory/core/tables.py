import pandas as pd
from zoneinfo import ZoneInfo

from db.inventory.core.constants import (
    BLACK_WHITE_COLOR_ORDER,
    BLACK_WHITE_MATERIAL_ORDER,
    DEFAULT_CATEGORY,
    DEFAULT_DEPARTMENT,
    SIZE_COLUMNS,
    UV_MATERIAL_ORDER,
    UV_MODEL_ORDER,
)


def get_inventory_last_updated(df):
    if df.empty or "updated_at" not in df.columns:
        return None

    updated_at = pd.to_datetime(df["updated_at"], errors="coerce", utc=True).dropna()
    if updated_at.empty:
        return None

    return updated_at.max().tz_convert(ZoneInfo("America/New_York")).date()


def sort_inventory_table(df, category):
    if category != "黑白短袖" or df.empty:
        return df.sort_values("总库存", ascending=False)

    sorted_df = df.copy()
    sorted_df["_material_order"] = sorted_df["材质"].map(BLACK_WHITE_MATERIAL_ORDER).fillna(99)
    sorted_df["_color_order"] = sorted_df["颜色"].map(BLACK_WHITE_COLOR_ORDER).fillna(99)
    sort_columns = ["_material_order", "品牌", "_color_order"]
    if "成本" in sorted_df.columns:
        sort_columns.append("成本")
    sorted_df = sorted_df.sort_values(sort_columns, kind="stable")
    return sorted_df.drop(columns=["_material_order", "_color_order"])


def build_inventory_table(
    df, category=DEFAULT_CATEGORY, include_cost=False,
    department=DEFAULT_DEPARTMENT,
):
    if df.empty:
        cost_columns = ["成本"] if include_cost else []
        details = [*SIZE_COLUMNS] if department == DEFAULT_DEPARTMENT else ["型号"]
        return pd.DataFrame(columns=[
            "品类", "品牌", "材质", "颜色", *cost_columns,
            *details, "总库存",
        ])

    inventory_df = df.copy()
    if include_cost and "unit_cost" not in inventory_df.columns:
        inventory_df["unit_cost"] = 0
    for column in ["category", "brand", "material"]:
        if column not in inventory_df.columns:
            inventory_df[column] = ""
        inventory_df[column] = inventory_df[column].fillna("").astype(str)
    if include_cost:
        inventory_df["unit_cost"] = pd.to_numeric(inventory_df["unit_cost"], errors="coerce").fillna(0)

    if department != DEFAULT_DEPARTMENT:
        return _build_model_inventory_table(inventory_df, include_cost)

    index_columns = ["category", "brand", "material", "color"]
    if include_cost:
        index_columns.append("unit_cost")
    pivot_df = (
        inventory_df
        .pivot_table(
            index=index_columns, columns="size", values="quantity",
            aggfunc="sum", fill_value=0,
        )
        .reset_index()
        .rename(columns={
            "category": "品类",
            "brand": "品牌",
            "material": "材质",
            "color": "颜色",
            "unit_cost": "成本",
        })
    )
    for size in SIZE_COLUMNS:
        if size not in pivot_df.columns:
            pivot_df[size] = 0
        pivot_df[size] = pd.to_numeric(pivot_df[size], errors="coerce").fillna(0).astype(int)

    pivot_df["总库存"] = pivot_df[SIZE_COLUMNS].sum(axis=1)
    cost_columns = ["成本"] if include_cost else []
    display_df = pivot_df[["品类", "品牌", "材质", "颜色", *cost_columns, *SIZE_COLUMNS, "总库存"]]
    return sort_inventory_table(display_df, category).reset_index(drop=True)


def _build_model_inventory_table(inventory_df, include_cost=False):
    index_columns = ["category", "brand", "material", "color", "size"]
    if include_cost:
        index_columns.append("unit_cost")
    result = (
        inventory_df.groupby(index_columns, dropna=False, as_index=False)
        .agg(quantity=("quantity", "sum"))
        .rename(columns={
            "category": "品类", "brand": "品牌", "material": "材质",
            "color": "颜色", "size": "型号", "unit_cost": "成本",
            "quantity": "总库存",
        })
    )
    result["型号"] = result["型号"].fillna("").astype(str).map(
        lambda value: "yuan" if value.upper() == "YUAN" else value
    )
    result["总库存"] = pd.to_numeric(
        result["总库存"], errors="coerce"
    ).fillna(0).astype(int)
    model_order = {value: index for index, value in enumerate(UV_MODEL_ORDER)}
    result["_material_order"] = result["材质"].map(
        UV_MATERIAL_ORDER
    ).fillna(99)
    result["_model_order"] = (
        result["型号"].str.upper().map(model_order).fillna(99)
    )
    return (
        result.sort_values(
            ["_material_order", "_model_order", "型号"], kind="stable"
        )
        .drop(columns=["_material_order", "_model_order"])
        .reset_index(drop=True)
    )


def build_color_inventory_table(inventory_df):
    if inventory_df.empty:
        return pd.DataFrame(columns=["颜色", *SIZE_COLUMNS, "总库存"])

    color_df = inventory_df.groupby("颜色", as_index=False)[SIZE_COLUMNS].sum()
    for size in SIZE_COLUMNS:
        color_df[size] = pd.to_numeric(color_df[size], errors="coerce").fillna(0).astype(int)
    color_df["总库存"] = color_df[SIZE_COLUMNS].sum(axis=1)
    color_df["_color_order"] = color_df["颜色"].map(BLACK_WHITE_COLOR_ORDER).fillna(99)
    return (
        color_df[["颜色", *SIZE_COLUMNS, "总库存", "_color_order"]]
        .sort_values(["_color_order", "颜色"], kind="stable")
        .drop(columns=["_color_order"])
        .reset_index(drop=True)
    )
