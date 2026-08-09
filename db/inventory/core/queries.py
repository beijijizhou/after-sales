import pandas as pd

from db.inventory.core.constants import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT
from db.inventory.core.pagination import fetch_range_pages


def load_inventory_dimensions(supabase):
    response = (
        supabase.table("inventory_items")
        .select("department,category,brand,material,color,size")
        .eq("is_active", True)
        .execute()
    )
    inventory = pd.DataFrame(response.data)
    try:
        departments = pd.DataFrame(
            supabase.table("inventory_departments")
            .select("id,code")
            .eq("is_active", True)
            .execute()
            .data
        )
        categories = pd.DataFrame(
            supabase.table("inventory_categories")
            .select("department_id,name")
            .eq("is_active", True)
            .execute()
            .data
        )
    except Exception:
        return inventory
    if departments.empty:
        return inventory
    master = departments.rename(
        columns={"code": "department"}
    ).merge(
        categories,
        left_on="id",
        right_on="department_id",
        how="left",
    ).rename(columns={"name": "category"})
    for column in ["brand", "material", "color", "size"]:
        master[column] = ""
    columns = [
        "department", "category", "brand", "material", "color", "size"
    ]
    return pd.concat(
        [inventory, master[columns]], ignore_index=True
    ).drop_duplicates().reset_index(drop=True)


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


def load_inventory_items(
    supabase, department=DEFAULT_DEPARTMENT, category=DEFAULT_CATEGORY,
    active_only=True,
):
    query = (
        supabase
        .table("inventory_items")
        .select("department,category,brand,material,color,size,unit_cost,quantity,updated_at")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    if active_only:
        query = query.eq("is_active", True)
    response = query.execute()
    return pd.DataFrame(response.data)


def load_inventory_movements(supabase, department=DEFAULT_DEPARTMENT, category=DEFAULT_CATEGORY, limit=20):
    columns = (
        "department,category,brand,material,color,size,quantity_change,"
        "quantity_after,movement_date,reason,created_at,created_by,"
        "batch_id,reversal_of_batch_id,source_type"
    )
    def fetch_page(selected_columns, start, end):
        query = (
            supabase.table("inventory_movements")
            .select(selected_columns)
            .eq("department", department)
        )
        if category:
            query = query.eq("category", category)
        return (
            query.order("movement_date", desc=True)
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
            .data
        )

    try:
        rows = fetch_range_pages(
            lambda start, end: fetch_page(columns, start, end), limit
        )
    except Exception:
        fallback_columns = columns.replace(
            ",created_by,batch_id,reversal_of_batch_id,source_type", ""
        )
        rows = fetch_range_pages(
            lambda start, end: fetch_page(
                fallback_columns, start, end
            ),
            limit,
        )
    return pd.DataFrame(rows)


def load_latest_inventory_movement_date(
    supabase, department, category="", brands=None, materials=None,
    colors=None, sizes=None,
):
    query = (
        supabase.table("inventory_movements")
        .select("movement_date")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    for column, values in [
        ("brand", brands),
        ("material", materials),
        ("color", colors),
        ("size", sizes),
    ]:
        if values:
            query = query.in_(column, list(values))
    rows = (
        query.order("movement_date", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    parsed = pd.to_datetime(
        rows[0].get("movement_date"), errors="coerce"
    )
    return None if pd.isna(parsed) else parsed.date()


def load_recent_inventory_outbound(
    supabase, department, start_date, category=None, limit=5000
):
    query = (
        supabase.table("inventory_movements")
        .select(
            "department,category,brand,material,color,size,"
            "quantity_change,movement_date"
        )
        .eq("department", department)
        .lt("quantity_change", 0)
        .gte("movement_date", start_date.isoformat())
    )
    if category:
        query = query.eq("category", category)
    response = query.limit(limit).execute()
    return pd.DataFrame(response.data)
