import pandas as pd


INVENTORY_COST_SCOPE_COLUMNS = [
    "department", "category", "brand", "material", "color",
]


def update_inventory_unit_costs(
    supabase, department, category, cost_df, inventory_df
):
    if cost_df.empty:
        return 0

    inventory = inventory_df.copy()
    inventory["unit_cost"] = pd.to_numeric(
        inventory.get("unit_cost", 0), errors="coerce"
    ).fillna(0)
    inventory["quantity"] = pd.to_numeric(
        inventory.get("quantity", 0), errors="coerce"
    ).fillna(0)
    valid_keys = set(
        inventory.loc[
            (inventory["unit_cost"] <= 0) & (inventory["quantity"] > 0),
            ["category", "brand", "material", "color", "size"],
        ].itertuples(index=False, name=None)
    )

    updated = 0
    for row in cost_df.to_dict("records"):
        row_category = row.get("品类") or category
        key = (
            row_category, row["品牌"], row["材质"], row["颜色"], row["尺码"]
        )
        unit_cost = pd.to_numeric(row["成本"], errors="coerce")
        if key not in valid_keys or pd.isna(unit_cost) or unit_cost <= 0:
            continue
        response = (
            supabase.table("inventory_items")
            .update({"unit_cost": float(unit_cost)})
            .eq("department", department)
            .eq("category", row_category)
            .eq("brand", row["品牌"])
            .eq("material", row["材质"])
            .eq("color", row["颜色"])
            .eq("size", row["尺码"])
            .execute()
        )
        updated += len(response.data or [])
    return updated


def fill_missing_inventory_group_costs(supabase, groups, unit_cost):
    """Apply a batch reference price to current stock without overwriting costs."""
    value = float(unit_cost)
    if value <= 0:
        raise ValueError("库存成本必须大于 0")
    targets = pd.DataFrame(groups).copy()
    if targets.empty:
        return 0
    missing = [
        column for column in INVENTORY_COST_SCOPE_COLUMNS
        if column not in targets.columns
    ]
    if missing:
        raise ValueError(f"缺少库存成本范围：{', '.join(missing)}")

    updated = 0
    targets = targets[INVENTORY_COST_SCOPE_COLUMNS].drop_duplicates()
    for target in targets.to_dict("records"):
        query = supabase.table("inventory_items").select(
            "id,quantity,unit_cost"
        )
        for column in INVENTORY_COST_SCOPE_COLUMNS:
            query = query.eq(column, target[column])
        rows = query.gt("quantity", 0).execute().data or []
        ids = [
            row["id"] for row in rows
            if pd.isna(pd.to_numeric(row.get("unit_cost"), errors="coerce"))
            or float(row.get("unit_cost") or 0) <= 0
        ]
        if not ids:
            continue
        response = (
            supabase.table("inventory_items")
            .update({"unit_cost": value}).in_("id", ids).execute()
        )
        updated += len(response.data or ids)
    return updated


def fill_missing_inventory_sku_costs(supabase, rows):
    """Fill current SKU costs from row-specific prices without overwrites."""
    required = [
        *INVENTORY_COST_SCOPE_COLUMNS, "size", "unit_cost",
    ]
    targets = pd.DataFrame(rows).copy()
    if targets.empty:
        return 0
    missing = [column for column in required if column not in targets.columns]
    if missing:
        raise ValueError(f"缺少库存成本字段：{', '.join(missing)}")
    targets = targets[required].drop_duplicates()
    updated = 0
    for target in targets.to_dict("records"):
        value = float(target["unit_cost"])
        if value <= 0:
            continue
        query = supabase.table("inventory_items").select(
            "id,quantity,unit_cost"
        )
        for column in [*INVENTORY_COST_SCOPE_COLUMNS, "size"]:
            query = query.eq(column, target[column])
        current = query.gt("quantity", 0).execute().data or []
        ids = [
            row["id"] for row in current
            if pd.isna(pd.to_numeric(row.get("unit_cost"), errors="coerce"))
            or float(row.get("unit_cost") or 0) <= 0
        ]
        if not ids:
            continue
        response = (
            supabase.table("inventory_items")
            .update({"unit_cost": value}).in_("id", ids).execute()
        )
        updated += len(response.data or ids)
    return updated
