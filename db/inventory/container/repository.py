import pandas as pd

from db.inventory.container.tables import normalize_container_rows


def load_inventory_containers(
    supabase, start_date=None, end_date=None, department=None, category=None,
    statuses=None, date_field="expected_arrival_date",
):
    columns = (
        "container_key,shipped_date,expected_arrival_date,actual_arrival_date,"
        "container_no,department,category,"
        "brand,material,color,size,quantity,unit_cost,status,note,created_at"
    )
    query = supabase.table("inventory_container_imports").select(columns)
    query = apply_container_filters(
        query, start_date, end_date, department, category, statuses, date_field
    )
    try:
        response = (
            query.order("expected_arrival_date", desc=False)
            .order("created_at", desc=False)
            .execute()
        )
        return pd.DataFrame(response.data)
    except Exception as error:
        message = str(error)
        if "container_key" not in message and "actual_arrival_date" not in message:
            raise

    legacy_columns = (
        "id,shipped_date,expected_arrival_date,container_no,department,category,"
        "brand,material,color,size,quantity,unit_cost,status,note,created_at"
    )
    legacy_query = supabase.table("inventory_container_imports").select(
        legacy_columns
    )
    legacy_query = apply_container_filters(
        legacy_query, start_date, end_date, department, category, statuses, date_field
    )
    response = (
        legacy_query.order("expected_arrival_date", desc=False)
        .order("created_at", desc=False)
        .execute()
    )
    result = pd.DataFrame(response.data)
    if result.empty:
        return result
    normalized_no = result["container_no"].fillna("").astype(str).str.upper()
    normalized_no = normalized_no.str.replace(r"\s+", "", regex=True)
    result["container_key"] = normalized_no.where(normalized_no != "", result["id"])
    result["actual_arrival_date"] = None
    return result.drop(columns=["id"])


def apply_container_filters(
    query, start_date, end_date, department, category, statuses, date_field
):
    if start_date is not None:
        query = query.gte(date_field, start_date.isoformat())
    if end_date is not None:
        query = query.lte(date_field, end_date.isoformat())
    if department:
        query = query.eq("department", department)
    if category:
        query = query.eq("category", category)
    if statuses:
        query = query.in_("status", statuses)
    return query


def load_container_dimensions(supabase):
    response = (
        supabase.table("inventory_container_imports")
        .select("department,category")
        .limit(1000)
        .execute()
    )
    return pd.DataFrame(response.data)


def create_inventory_containers(supabase, df, operated_by="system"):
    records = []
    cleaned_df = normalize_container_rows(df)
    for row in cleaned_df.to_dict("records"):
        records.append({
            "container_key": row["货柜记录ID"],
            "shipped_date": row["发货日期"].isoformat(),
            "expected_arrival_date": row["预计到货日期"].isoformat(),
            "container_no": row["货柜号"] or None,
            "department": row["部门"],
            "category": row["品类"] or None,
            "brand": row["品牌"],
            "material": row["材质"],
            "color": row["颜色"],
            "size": row["尺码"],
            "quantity": int(row["数量"]),
            "unit_cost": float(row["成本"] or 0),
            "品牌": row["品牌"],
            "材质": row["材质"],
            "成本": float(row["成本"] or 0),
            "status": row["状态"],
            "note": row["备注"] or None,
        })
    if not records:
        return []
    response = supabase.table("inventory_container_imports").insert(records).execute()
    events = []
    for _, row in cleaned_df.drop_duplicates("货柜记录ID").iterrows():
        events.append({
            "container_key": row["货柜记录ID"],
            "container_no": row["货柜号"] or None,
            "event_type": "创建",
            "effective_date": row["发货日期"].isoformat(),
            "previous_status": None,
            "new_status": row["状态"],
            "operated_by": operated_by,
            "note": row["备注"] or None,
        })
    supabase.table("inventory_container_events").insert(events).execute()
    return response.data
