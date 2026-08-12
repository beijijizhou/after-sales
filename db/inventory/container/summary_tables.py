"""Container display columns and grouped inventory summaries."""

import pandas as pd

from db.inventory import SIZE_COLUMNS
from db.inventory.container.labels import get_container_display_label
from db.inventory.core.constants import UV_MODEL_ORDER


def build_container_inventory_summary(display_df):
    if display_df.empty:
        return pd.DataFrame()
    if "型号" in display_df.columns:
        items = ordered_item_columns(display_df["型号"])
        summary = display_df.pivot_table(
            index=["材质", "颜色"], columns="型号", values="数量",
            aggfunc="sum", fill_value=0,
        ).reset_index()
        front = ["材质", "颜色"]
    else:
        items = get_container_item_columns(display_df)
        summary = display_df.groupby(
            "颜色", dropna=False, as_index=False
        )[items].sum()
        front = ["颜色"]
    for item in items:
        if item not in summary:
            summary[item] = 0
        summary[item] = pd.to_numeric(
            summary[item], errors="coerce"
        ).fillna(0).astype(int)
    summary["总件数"] = summary[items].sum(axis=1)
    if "颜色" in summary:
        order = summary["颜色"].map({"黑": 0, "白": 1}).fillna(99)
        summary = summary.assign(_color_order=order).sort_values(
            ["_color_order", *front], kind="stable"
        ).drop(columns="_color_order")
    return summary[[*front, *items, "总件数"]].reset_index(drop=True)


def build_filtered_container_summary(raw_df):
    front = ["涉及货柜", "部门", "品类", "品牌", "材质", "颜色"]
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=[*front, "总件数"])
    source = raw_df.copy()
    source["quantity"] = pd.to_numeric(
        source["quantity"], errors="coerce"
    ).fillna(0)
    fields = [
        "container_key", "container_no", "department", "category", "brand",
        "material", "color", "size",
    ]
    for column in fields:
        source[column] = source[column].fillna("").astype(str).str.strip()
    source["涉及货柜"] = source.apply(
        lambda row: get_container_display_label(
            row["container_key"], row["container_no"], [row.get("note", "")]
        ), axis=1,
    )
    group_keys = ["department", "category", "brand", "material", "color"]
    labels = source.groupby(group_keys, dropna=False, as_index=False).agg(
        涉及货柜=("涉及货柜", lambda values: "、".join(dict.fromkeys(
            value for value in values if value
        )))
    )
    grouped = source.groupby(
        [*group_keys, "size"], dropna=False, as_index=False
    ).agg(数量=("quantity", "sum"))
    items = ordered_item_columns(grouped["size"])
    quantities = grouped.pivot_table(
        index=group_keys, columns="size", values="数量",
        aggfunc="sum", fill_value=0,
    ).reset_index()
    names = {
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色",
    }
    result = quantities.rename(columns=names).merge(
        labels.rename(columns=names),
        on=["部门", "品类", "品牌", "材质", "颜色"], how="left",
    )
    for item in items:
        if item not in result:
            result[item] = 0
        result[item] = pd.to_numeric(
            result[item], errors="coerce"
        ).fillna(0).astype(int)
    result["总件数"] = result[items].sum(axis=1)
    return result[[*front, *items, "总件数"]].sort_values(
        ["部门", "品类", "品牌", "材质", "颜色"], kind="stable",
    ).reset_index(drop=True)


def container_display_columns(include_cost, item_columns=None):
    cost = ["成本"] if include_cost else []
    items = item_columns or SIZE_COLUMNS
    return [
        "货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期",
        "实际到货日期", "实际到货时间（纽约）", "确认到柜时间（纽约）",
        "货柜号", "部门", "品类", "品牌", "材质", "颜色", *cost,
        *items, "总件数", "状态", "备注",
    ]


def get_container_item_columns(display_df):
    metadata = {
        "货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期",
        "实际到货日期", "实际到货时间（纽约）", "确认到柜时间（纽约）",
        "货柜号", "部门", "品类", "品牌", "材质", "颜色", "成本",
        "总件数", "状态", "备注", "型号", "数量",
    }
    return [column for column in display_df.columns if column not in metadata]


def ordered_item_columns(values):
    available = {
        str(value).strip() for value in values
        if pd.notna(value) and str(value).strip()
    }
    preferred = [*SIZE_COLUMNS, *UV_MODEL_ORDER]
    ordered = [value for value in preferred if value in available]
    return [*ordered, *sorted(available - set(ordered))] or SIZE_COLUMNS
