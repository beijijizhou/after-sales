import pandas as pd


def load_warehouses(supabase):
    rows = (
        supabase.table("inventory_warehouses")
        .select("code,name,purpose,sort_order,is_active")
        .eq("is_active", True)
        .order("sort_order")
        .execute().data or []
    )
    return pd.DataFrame(rows)


def load_warehouse_inventory_items(supabase, active_only=True):
    query = (
        supabase.table("inventory_items")
        .select(
            "id,department,category,brand,material,color,size,quantity"
        )
    )
    if active_only:
        query = query.eq("is_active", True)
    rows = (
        query.order("department").order("category").execute().data or []
    )
    return pd.DataFrame(rows)


def load_warehouse_balances(supabase):
    rows = (
        supabase.table("inventory_warehouse_balances")
        .select(
            "inventory_item_id,warehouse_code,quantity,location_note,updated_at"
        )
        .execute().data or []
    )
    return pd.DataFrame(rows)


def load_transfer_orders(supabase, limit=200):
    rows = (
        supabase.table("inventory_transfer_orders")
        .select(
            "id,transfer_number,from_warehouse,to_warehouse,status,note,"
            "created_by,created_at,dispatched_by,dispatched_at,"
            "received_by,received_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute().data or []
    )
    return pd.DataFrame(rows)


def load_transfer_lines(supabase, order_id=None):
    query = supabase.table("inventory_transfer_lines").select(
        "id,transfer_order_id,inventory_item_id,quantity_sent,"
        "quantity_received,source_location,target_location,note"
    )
    if order_id:
        query = query.eq("transfer_order_id", str(order_id))
    lines = pd.DataFrame(query.execute().data or [])
    if lines.empty:
        return lines
    items = load_warehouse_inventory_items(supabase, active_only=False)
    return lines.merge(
        items.rename(columns={"id": "inventory_item_id"}),
        on="inventory_item_id", how="left",
    )


def create_transfer_request(
    supabase, from_warehouse, to_warehouse, item_ids, note, created_by,
):
    lines = [
        {"inventory_item_id": str(item_id)}
        for item_id in dict.fromkeys(item_ids)
    ]
    return supabase.rpc("create_inventory_transfer_request", {
        "p_from_warehouse": from_warehouse or None,
        "p_to_warehouse": to_warehouse,
        "p_lines": lines,
        "p_note": note or None,
        "p_created_by": created_by,
    }).execute().data


def dispatch_transfer(
    supabase, order_id, from_warehouse, lines, operated_by,
):
    return supabase.rpc("dispatch_inventory_transfer", {
        "p_order_id": str(order_id),
        "p_from_warehouse": from_warehouse,
        "p_lines": lines,
        "p_operated_by": operated_by,
    }).execute().data


def receive_transfer(supabase, order_id, lines, operated_by):
    return supabase.rpc("receive_inventory_transfer", {
        "p_order_id": str(order_id),
        "p_lines": lines,
        "p_operated_by": operated_by,
    }).execute().data


def complete_transfer_direct(
    supabase, from_warehouse, to_warehouse, lines, note, operated_by,
):
    return supabase.rpc("complete_inventory_transfer_direct", {
        "p_from_warehouse": from_warehouse,
        "p_to_warehouse": to_warehouse,
        "p_lines": lines,
        "p_note": note or None,
        "p_operated_by": operated_by,
    }).execute().data


def complete_pending_transfer(
    supabase, order_id, from_warehouse, lines, operated_by,
):
    return supabase.rpc("complete_pending_inventory_transfer", {
        "p_order_id": str(order_id),
        "p_from_warehouse": from_warehouse,
        "p_lines": lines,
        "p_operated_by": operated_by,
    }).execute().data


def save_location_note(supabase, inventory_item_id, warehouse_code, note):
    return supabase.rpc("set_inventory_warehouse_location", {
        "p_inventory_item_id": str(inventory_item_id),
        "p_warehouse_code": warehouse_code,
        "p_location_note": str(note or "").strip(),
    }).execute().data


def reverse_transfer(supabase, order_id, operated_by):
    return supabase.rpc("reverse_inventory_transfer", {
        "p_order_id": str(order_id),
        "p_operated_by": operated_by,
    }).execute().data
