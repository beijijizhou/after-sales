import pandas as pd

from utils.erp.inventory_mapping import normalize_production_for_inventory


COLOR_TARGETS = {
    "浅灰": "灰色",
}
ALLOCATION_COLUMNS = [
    "品牌", "材质", "颜色", "尺码",
    "当前库存", "预计扣减", "扣减后库存", "状态",
]


def build_colored_tshirt_inventory_review(production_df, inventory_df):
    source_map = _build_source_map(production_df, inventory_df)
    demand = (
        source_map[source_map["映射状态"] == "已匹配"]
        .groupby(["库存颜色", "库存尺码"], as_index=False)["生产数量"]
        .sum()
    )
    allocation = _allocate_inventory(demand, inventory_df)
    return source_map, allocation


def _build_source_map(production_df, inventory_df):
    if production_df.empty:
        return pd.DataFrame()
    normalized = normalize_production_for_inventory(production_df)
    normalized = normalized[
        (normalized["department"] == "DTF")
        & (normalized["category"] == "彩色短袖")
    ].copy()
    if "生产项状态" in normalized:
        normalized = normalized[
            ~normalized["生产项状态"].astype(str).str.contains(
                "取消", na=False
            )
        ]
    if normalized.empty:
        return pd.DataFrame()

    inventory_colors = _values(inventory_df, "color")
    inventory_sizes = _values(inventory_df, "size")
    normalized["生产平台"] = _column(normalized, "运营商", "未知平台")
    normalized["生产材质"] = _column(normalized, "material")
    normalized["生产颜色"] = _column(normalized, "color")
    normalized["生产尺码"] = _column(normalized, "size")
    normalized["库存颜色"] = normalized["生产颜色"].map(
        lambda value: COLOR_TARGETS.get(value, value)
    )
    normalized["库存尺码"] = normalized["生产尺码"]
    normalized["生产数量"] = pd.to_numeric(
        normalized["quantity"], errors="coerce"
    ).fillna(0).astype(int)
    normalized["映射状态"] = normalized.apply(
        lambda row: _mapping_status(
            row["库存颜色"], row["库存尺码"],
            inventory_colors, inventory_sizes,
        ),
        axis=1,
    )
    columns = [
        "生产平台", "生产材质", "生产颜色", "生产尺码",
        "库存颜色", "库存尺码", "映射状态",
    ]
    return (
        normalized.groupby(columns, dropna=False, as_index=False)
        .agg(生产数量=("生产数量", "sum"))
        [[*columns[:4], "生产数量", *columns[4:]]]
        .sort_values(
            ["映射状态", "生产数量"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )


def _allocate_inventory(demand_df, inventory_df):
    if demand_df.empty:
        return pd.DataFrame(columns=ALLOCATION_COLUMNS)
    inventory = inventory_df.copy()
    inventory["quantity"] = pd.to_numeric(
        inventory.get("quantity", 0), errors="coerce"
    ).fillna(0).astype(int)
    inventory["_priority"] = inventory.get(
        "brand", pd.Series("", index=inventory.index)
    ).fillna("").astype(str).str.strip().ne("临时进货").astype(int)
    inventory = inventory.sort_values(
        ["_priority", "brand", "material", "color", "size"]
    )
    rows = []
    for demand in demand_df.to_dict("records"):
        remaining = int(demand["生产数量"])
        candidates = inventory[
            (inventory["color"] == demand["库存颜色"])
            & (inventory["size"] == demand["库存尺码"])
            & (inventory["quantity"] > 0)
        ]
        for item in candidates.to_dict("records"):
            if remaining <= 0:
                break
            deduction = min(remaining, int(item["quantity"]))
            rows.append(_allocation_row(item, deduction))
            remaining -= deduction
        if remaining > 0:
            rows.append({
                "品牌": "未匹配库存",
                "材质": "",
                "颜色": demand["库存颜色"],
                "尺码": demand["库存尺码"],
                "当前库存": 0,
                "预计扣减": remaining,
                "扣减后库存": -remaining,
                "状态": "库存不足",
            })
    return pd.DataFrame(rows, columns=ALLOCATION_COLUMNS)


def _allocation_row(item, deduction):
    stock = int(item["quantity"])
    return {
        "品牌": str(item.get("brand") or "").strip(),
        "材质": str(item.get("material") or "").strip(),
        "颜色": str(item.get("color") or "").strip(),
        "尺码": str(item.get("size") or "").strip(),
        "当前库存": stock,
        "预计扣减": deduction,
        "扣减后库存": stock - deduction,
        "状态": "可扣减",
    }


def _mapping_status(color, size, inventory_colors, inventory_sizes):
    if not color or color not in inventory_colors:
        return "颜色未映射"
    if not size or size not in inventory_sizes:
        return "尺码未映射"
    return "已匹配"


def _values(df, column):
    if df.empty or column not in df:
        return set()
    return {
        str(value).strip()
        for value in df[column].dropna()
        if str(value).strip()
    }


def _column(df, column, default=""):
    if column not in df:
        return pd.Series(default, index=df.index)
    result = df[column].fillna("").astype(str).str.strip()
    return result.mask(result == "", default) if default else result
