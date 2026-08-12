"""Missing-cost queues and audited unit-cost maintenance."""

from datetime import date, timedelta

import pandas as pd

from db.finance.repository import _fetch_pages, _normalize_cost_rows


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
            .is_("reversed_at", "null").is_("unit_cost", "null")
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


def update_inbound_lot_cost(supabase, cost_lot_id, unit_cost):
    unit_cost = float(unit_cost)
    if unit_cost <= 0:
        raise ValueError("批次成本必须大于 0")
    lot = (
        supabase.table("inventory_cost_lots")
        .select("id,inbound_movement_id,reversed_at")
        .eq("id", cost_lot_id).single().execute().data
    )
    if not lot or lot.get("reversed_at"):
        raise ValueError("找不到有效的入库成本批次")
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
