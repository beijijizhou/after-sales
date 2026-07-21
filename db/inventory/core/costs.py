import pandas as pd


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
