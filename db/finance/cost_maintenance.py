"""Missing-cost queues and audited unit-cost maintenance."""

from datetime import date, timedelta

import pandas as pd

from db.finance.repository import _fetch_pages, _normalize_cost_rows


def load_inbound_cost_history(supabase):
    """Load every active inbound cost record for the shared cost ledger."""
    rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_lots")
            .select(
                "id,inbound_movement_id,batch_id,received_quantity,"
                "remaining_quantity,unit_cost,source_type,movement_date,"
                "created_at,reversed_at,inventory_items!"
                "inventory_cost_lots_inventory_item_id_fkey!inner"
                "(department,category,brand,material,color,size)"
            )
            .is_("reversed_at", "null")
            .order("movement_date", desc=True).order("id")
            .range(start, end).execute().data
        )
    )
    inventory = _normalize_cost_rows(
        rows, "inventory_items", "received_quantity", "入库",
        date_column="movement_date",
    )
    inventory = exclude_stocktake_batches(supabase, inventory)
    if not inventory.empty:
        from db.finance.inbound_linking import attach_container_batches

        inventory = attach_container_batches(
            supabase, inventory, date(2000, 1, 1),
            date.today() + timedelta(days=1),
        )

    from db.finance.consumable_repository import (
        load_consumable_frames, normalize_consumable_finance_rows,
    )

    consumables = normalize_consumable_finance_rows(
        *load_consumable_frames(supabase),
        date(2000, 1, 1), date.today() + timedelta(days=1),
    )
    if not consumables.empty:
        consumables = consumables[consumables["direction"] == "入库"]
    return pd.concat([inventory, consumables], ignore_index=True)


def load_missing_inventory_cost_lots(supabase):
    rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_lots")
            .select(
                "id,inbound_movement_id,batch_id,received_quantity,"
                "remaining_quantity,unit_cost,source_type,movement_date,"
                "created_at,reversed_at,inventory_items!"
                "inventory_cost_lots_inventory_item_id_fkey!inner"
                "(department,category,brand,material,color,size)"
            )
            .is_("reversed_at", "null")
            .or_("unit_cost.is.null,unit_cost.eq.0")
            .order("movement_date", desc=True).order("id")
            .range(start, end).execute().data
        )
    )
    inventory = _normalize_cost_rows(
        rows, "inventory_items", "received_quantity", "入库",
        date_column="movement_date",
    )
    inventory = exclude_stocktake_batches(supabase, inventory)
    return pd.concat(
        [inventory, load_missing_consumable_cost_movements(supabase)],
        ignore_index=True,
    )


def exclude_stocktake_batches(supabase, rows):
    """Inventory settings are corrections, not purchasing/inbound finance."""
    if rows.empty or "batch_id" not in rows:
        return rows
    batch_ids = [
        value for value in rows["batch_id"].dropna().astype(str).unique()
        if value
    ]
    if not batch_ids:
        return rows
    try:
        stocktakes = (
            supabase.table("inventory_stocktake_batches").select("batch_id")
            .in_("batch_id", batch_ids).execute().data
        )
    except Exception as exc:
        if "inventory_stocktake_batches" in str(exc) and "PGRST205" in str(exc):
            return rows
        raise
    excluded = {str(row["batch_id"]) for row in stocktakes}
    return rows[
        ~rows["batch_id"].fillna("").astype(str).isin(excluded)
    ].reset_index(drop=True) if excluded else rows


def load_missing_consumable_cost_movements(supabase):
    from db.finance.consumable_repository import (
        load_consumable_frames, normalize_consumable_finance_rows,
    )

    frames = load_consumable_frames(supabase)
    rows = normalize_consumable_finance_rows(
        *frames, date(2000, 1, 1), date.today() + timedelta(days=1)
    )
    if rows.empty:
        return rows
    return rows[
        (rows["direction"] == "入库") & rows["missing_cost"]
    ].reset_index(drop=True)


def load_inventory_batch_cost_lots(supabase, batch_id):
    """Load active cost lots belonging to one inventory movement batch."""
    rows = (
        supabase.table("inventory_cost_lots")
        .select(
            "id,inbound_movement_id,batch_id,received_quantity,unit_cost,"
            "inventory_items!inventory_cost_lots_inventory_item_id_fkey!inner"
            "(department,category,brand,material,color,size)"
        )
        .eq("batch_id", str(batch_id))
        .is_("reversed_at", "null")
        .order("id")
        .execute().data or []
    )
    normalized = pd.json_normalize(rows, sep=".")
    columns = [
        "record_id", "movement_id", "batch_id", "quantity", "unit_cost",
        "department", "category", "brand", "material", "color", "size",
    ]
    if normalized.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame({
        "record_id": normalized["id"],
        "movement_id": normalized["inbound_movement_id"],
        "batch_id": normalized["batch_id"],
        "quantity": pd.to_numeric(
            normalized["received_quantity"], errors="coerce"
        ).fillna(0),
        "unit_cost": pd.to_numeric(
            normalized["unit_cost"], errors="coerce"
        ),
        "department": normalized["inventory_items.department"],
        "category": normalized["inventory_items.category"],
        "brand": normalized["inventory_items.brand"],
        "material": normalized["inventory_items.material"],
        "color": normalized["inventory_items.color"],
        "size": normalized["inventory_items.size"],
    })[columns]


def update_inbound_lot_cost(
    supabase, cost_lot_id, unit_cost, operated_by="system",
):
    unit_cost = float(unit_cost)
    if unit_cost <= 0:
        raise ValueError("批次成本必须大于 0")
    lot = (
        supabase.table("inventory_cost_lots")
        .select(
            "id,inbound_movement_id,batch_id,received_quantity,unit_cost,"
            "reversed_at,inventory_items!"
            "inventory_cost_lots_inventory_item_id_fkey!inner"
            "(department,category,brand,material,color,size)"
        )
        .eq("id", cost_lot_id).single().execute().data
    )
    if not lot or lot.get("reversed_at"):
        raise ValueError("找不到有效的入库成本批次")
    previous_cost = float(lot.get("unit_cost") or 0)
    allocations = (
        supabase.table("inventory_cost_allocations")
        .select("id,unit_cost").eq("cost_lot_id", cost_lot_id)
        .is_("reversed_at", "null").execute()
    ).data or []
    previous_movement = None
    if lot.get("inbound_movement_id"):
        previous_movement = (
            supabase.table("inventory_movements")
            .select("id,unit_cost,成本")
            .eq("id", lot["inbound_movement_id"]).single().execute().data
        )
    item = lot.get("inventory_items") or {}
    old_snapshot = {
        **item,
        "event_type": "批次成本更正",
        "cost_lot_id": str(lot["id"]),
        "batch_id": str(lot.get("batch_id") or ""),
        "unit_cost": previous_cost,
    }
    new_snapshot = {**old_snapshot, "unit_cost": unit_cost}
    try:
        supabase.table("inventory_cost_lots").update(
            {"unit_cost": unit_cost}
        ).eq("id", cost_lot_id).execute()
        (
            supabase.table("inventory_cost_allocations")
            .update({"unit_cost": unit_cost}).eq("cost_lot_id", cost_lot_id)
            .is_("reversed_at", "null").execute()
        )
        if lot.get("inbound_movement_id"):
            (
                supabase.table("inventory_movements")
                .update({"unit_cost": unit_cost, "成本": unit_cost})
                .eq("id", lot["inbound_movement_id"]).execute()
            )
        supabase.table("inventory_sku_change_log").insert({
            "department": str(item.get("department") or ""),
            "old_identity": old_snapshot,
            "new_identity": new_snapshot,
            "affected_items": 1,
            "affected_quantity": int(lot.get("received_quantity") or 0),
            "changed_by": str(operated_by or "system").strip() or "system",
        }).execute()
    except Exception:
        supabase.table("inventory_cost_lots").update(
            {"unit_cost": previous_cost}
        ).eq("id", cost_lot_id).execute()
        for allocation in allocations:
            (
                supabase.table("inventory_cost_allocations")
                .update({"unit_cost": allocation.get("unit_cost")})
                .eq("id", allocation["id"]).execute()
            )
        if previous_movement:
            (
                supabase.table("inventory_movements")
                .update({
                    "unit_cost": previous_movement.get("unit_cost"),
                    "成本": previous_movement.get("成本"),
                })
                .eq("id", previous_movement["id"]).execute()
            )
        raise
    return True


def update_consumable_movement_cost(supabase, movement_id, unit_cost):
    unit_cost = float(unit_cost)
    if unit_cost <= 0:
        raise ValueError("耗材单位成本必须大于 0")
    movement = (
        supabase.table("consumable_movements")
        .select("id,quantity_change,reversal_of_movement_id")
        .eq("id", movement_id).single().execute().data
    )
    if not movement or movement.get("reversal_of_movement_id"):
        raise ValueError("找不到有效的耗材入库记录")
    if float(movement.get("quantity_change") or 0) <= 0:
        raise ValueError("只有耗材入库记录可以填写单位成本")
    supabase.table("consumable_movements").update(
        {"unit_cost": unit_cost}
    ).eq("id", movement_id).execute()
    return True
