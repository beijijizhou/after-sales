"""Cross-domain inventory dashboard overview metrics."""

from datetime import timedelta

import pandas as pd

from db.consumables import load_consumable_items
from db.inventory.container.repository import load_inventory_containers


def load_inventory_overview(supabase, today):
    inventory = pd.DataFrame(
        supabase.table("inventory_items")
        .select("department,category,quantity").execute().data or []
    )
    quantities = pd.to_numeric(
        inventory.get("quantity", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0)
    consumables = load_consumable_items(supabase, active_only=True)
    current = pd.to_numeric(
        consumables.get("current_quantity", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0)
    minimum = pd.to_numeric(
        consumables.get("minimum_quantity", pd.Series(dtype=float)),
        errors="coerce",
    )
    low_consumables = int(
        (minimum.notna() & current.le(minimum.fillna(0))).sum()
    )
    containers = load_inventory_containers(
        supabase, statuses=["未到货", "延迟", "在途"]
    )
    count = (
        int(containers["container_key"].nunique())
        if not containers.empty and "container_key" in containers else 0
    )
    expected = pd.to_datetime(
        containers.get(
            "expected_arrival_date", pd.Series(dtype="datetime64[ns]")
        ), errors="coerce",
    ).dt.date
    delayed = int(
        containers.loc[expected.lt(today), "container_key"].nunique()
    ) if count else 0
    arriving = int(containers.loc[
        expected.ge(today) & expected.le(today + timedelta(days=7)),
        "container_key",
    ].nunique()) if count else 0
    return {
        "production_skus": len(inventory),
        "production_units": int(quantities.sum()),
        "zero_stock_skus": int(quantities.le(0).sum()),
        "consumable_skus": len(consumables),
        "low_consumable_skus": low_consumables,
        "in_transit_containers": count,
        "delayed_containers": delayed,
        "arriving_containers": arriving,
    }
