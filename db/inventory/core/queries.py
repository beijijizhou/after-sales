import pandas as pd

from db.inventory.core.constants import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT


def load_inventory_departments(supabase):
    response = (
        supabase
        .table("inventory_items")
        .select("department")
        .execute()
    )
    df = pd.DataFrame(response.data)
    if df.empty or "department" not in df.columns:
        return [DEFAULT_DEPARTMENT]

    departments = sorted({
        str(value).strip()
        for value in df["department"].dropna()
        if str(value).strip()
    })
    return departments or [DEFAULT_DEPARTMENT]


def load_inventory_items(supabase, department=DEFAULT_DEPARTMENT, category=DEFAULT_CATEGORY):
    query = (
        supabase
        .table("inventory_items")
        .select("department,category,brand,material,color,size,unit_cost,quantity,updated_at")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    response = query.execute()
    return pd.DataFrame(response.data)


def load_inventory_movements(supabase, department=DEFAULT_DEPARTMENT, category=DEFAULT_CATEGORY, limit=20):
    columns = (
        "department,category,brand,material,color,size,quantity_change,"
        "quantity_after,movement_date,reason,created_at,created_by,"
        "batch_id,reversal_of_batch_id"
    )
    query = supabase.table("inventory_movements").select(columns).eq("department", department)
    if category:
        query = query.eq("category", category)
    try:
        response = query.order("movement_date", desc=True).order(
            "created_at", desc=True
        ).limit(limit).execute()
    except Exception:
        fallback_columns = columns.replace(",created_by,batch_id,reversal_of_batch_id", "")
        query = supabase.table("inventory_movements").select(fallback_columns).eq(
            "department", department
        )
        if category:
            query = query.eq("category", category)
        response = query.order("movement_date", desc=True).order(
            "created_at", desc=True
        ).limit(limit).execute()
    return pd.DataFrame(response.data)
