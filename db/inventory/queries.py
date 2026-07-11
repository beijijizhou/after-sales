import pandas as pd

from db.inventory.constants import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT


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
    query = (
        supabase
        .table("inventory_movements")
        .select("department,category,brand,material,color,size,quantity_change,quantity_after,movement_date,reason,created_at")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    response = (
        query
        .order("movement_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)
