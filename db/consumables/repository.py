from uuid import uuid4

import pandas as pd


ITEM_COLUMNS = [
    "id", "department_id", "category", "name", "specification", "brand",
    "base_unit", "package_unit", "units_per_package", "current_quantity",
    "minimum_quantity", "is_active", "created_by", "created_at", "updated_at",
]
BATCH_COLUMNS = [
    "id", "department_id", "movement_type", "movement_date",
    "total_quantity", "note", "source_file_name", "created_by", "created_at",
    "reversal_of_batch_id",
]
MOVEMENT_COLUMNS = [
    "id", "batch_id", "item_id", "movement_date", "quantity_change",
    "quantity_after", "unit_cost", "note", "created_by", "created_at",
    "reversal_of_movement_id",
]


def load_departments(supabase):
    response = (
        supabase.table("inventory_departments")
        .select("id,code,name")
        .eq("is_active", True)
        .order("code")
        .execute()
    )
    return pd.DataFrame(response.data, columns=["id", "code", "name"])


def load_consumable_items(supabase, department_id=None, active_only=False):
    query = supabase.table("consumable_items").select(",".join(ITEM_COLUMNS))
    if department_id:
        query = query.eq("department_id", department_id)
    if active_only:
        query = query.eq("is_active", True)
    response = query.order("category").order("name").execute()
    return pd.DataFrame(response.data, columns=ITEM_COLUMNS)


def create_consumable_item(supabase, values):
    return (
        supabase.table("consumable_items")
        .insert(values)
        .execute()
        .data
    )


def acknowledge_consumable_completion(
    supabase, department_id, movement_date, note, created_by,
):
    """Record an audited no-stock-change acknowledgement for one day."""
    return (
        supabase.table("consumable_movement_batches")
        .insert({
            "id": str(uuid4()),
            "department_id": str(department_id),
            "movement_type": "adjustment",
            "movement_date": movement_date.isoformat(),
            "total_quantity": 0,
            "note": str(note or "").strip(),
            "source_file_name": "completion_ack",
            "created_by": str(created_by or "system").strip() or "system",
        })
        .execute().data
    )


def update_consumable_item(supabase, item_id, values):
    return (
        supabase.table("consumable_items")
        .update(values)
        .eq("id", item_id)
        .execute()
        .data
    )


def load_consumable_batches(
    supabase, department_id=None, start_date=None, end_date=None, limit=500
):
    query = supabase.table("consumable_movement_batches").select(
        ",".join(BATCH_COLUMNS)
    )
    if department_id:
        query = query.eq("department_id", department_id)
    if start_date:
        query = query.gte("movement_date", start_date.isoformat())
    if end_date:
        query = query.lte("movement_date", end_date.isoformat())
    response = (
        query.order("movement_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data, columns=BATCH_COLUMNS)


def load_consumable_movements(supabase, batch_ids=None, limit=5000):
    query = supabase.table("consumable_movements").select(
        ",".join(MOVEMENT_COLUMNS)
    )
    if batch_ids:
        query = query.in_("batch_id", list(batch_ids))
    response = (
        query.order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data, columns=MOVEMENT_COLUMNS)
