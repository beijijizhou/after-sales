from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.container.tables import normalize_container_rows
from db.inventory.core.query_filters import apply_inventory_dimension_filters


CONTAINER_COLUMNS = (
    "id,container_key,shipped_date,expected_arrival_date,actual_arrival_date,"
    "actual_arrival_at,container_no,department,category,brand,material,color,"
    "size,quantity,unit_cost,status,note,created_at"
)


def load_inventory_containers(
    supabase, start_date=None, end_date=None, department=None, category=None,
    statuses=None, date_field="expected_arrival_date",
    brands=None, materials=None, colors=None, sizes=None,
):
    columns = CONTAINER_COLUMNS
    try:
        return _execute_container_query(
            supabase, columns, start_date, end_date, department, category,
            statuses, date_field, brands, materials, colors, sizes,
        )
    except Exception as error:
        message = str(error)
        if "actual_arrival_at" in message:
            compatible_columns = columns.replace("actual_arrival_at,", "")
            result = _execute_container_query(
                supabase, compatible_columns, start_date, end_date,
                department, category, statuses, date_field, brands,
                materials, colors, sizes,
            )
            result["actual_arrival_at"] = None
            return result
        if "container_key" not in message and "actual_arrival_date" not in message:
            raise

    legacy_columns = (
        "id,shipped_date,expected_arrival_date,container_no,department,category,"
        "brand,material,color,size,quantity,unit_cost,status,note,created_at"
    )
    result = _execute_container_query(
        supabase, legacy_columns, start_date, end_date, department, category,
        statuses, date_field, brands, materials, colors, sizes,
    )
    if result.empty:
        return result
    normalized_no = result["container_no"].fillna("").astype(str).str.upper()
    normalized_no = normalized_no.str.replace(r"\s+", "", regex=True)
    result["container_key"] = normalized_no.where(normalized_no != "", result["id"])
    result["actual_arrival_date"] = None
    result["actual_arrival_at"] = None
    return result.drop(columns=["id"])


def load_container_search_records(supabase):
    response = (
        supabase.table("inventory_container_imports")
        .select(CONTAINER_COLUMNS)
        .order("expected_arrival_date", desc=True)
        .order("created_at", desc=False)
        .limit(5000)
        .execute()
    )
    return pd.DataFrame(response.data)


def load_posted_container_by_inventory_batch(supabase, batch_id):
    """Resolve one posted container from its inventory movement batch."""
    events = (
        supabase.table("inventory_container_events")
        .select("container_key")
        .eq("event_type", "入库")
        .ilike("note", f"%库存批次：{batch_id}%")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not events:
        return pd.DataFrame()
    return (
        supabase.table("inventory_container_imports")
        .select(CONTAINER_COLUMNS)
        .eq("container_key", events[0]["container_key"])
        .execute()
        .data
    )


def _execute_container_query(
    supabase, columns, start_date, end_date, department, category,
    statuses, date_field, brands, materials, colors, sizes,
):
    query = supabase.table("inventory_container_imports").select(columns)
    query = apply_container_filters(
        query, start_date, end_date, department, category, statuses,
        date_field, brands, materials, colors, sizes,
    )
    response = (
        query.order("expected_arrival_date", desc=False)
        .order("created_at", desc=False)
        .execute()
    )
    return pd.DataFrame(response.data)


def apply_container_filters(
    query, start_date, end_date, department, category, statuses, date_field,
    brands=None, materials=None, colors=None, sizes=None,
):
    if start_date is not None:
        query = query.gte(date_field, start_date.isoformat())
    if end_date is not None:
        query = query.lte(date_field, end_date.isoformat())
    if statuses:
        query = query.in_("status", statuses)
    return apply_inventory_dimension_filters(
        query, department=department, category=category, brands=brands,
        materials=materials, colors=colors, sizes=sizes,
    )


def load_container_dimensions(supabase):
    response = (
        supabase.table("inventory_container_imports")
        .select("department,category,brand,material,color,size")
        .limit(5000)
        .execute()
    )
    return pd.DataFrame(response.data)


def create_inventory_containers(supabase, df, operated_by="system"):
    cleaned_df = normalize_container_rows(df)
    records = _container_records(cleaned_df)
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


def append_inventory_container_items(
    supabase, container_key, df, operated_by="system"
):
    """Append audited SKU rows to one editable business container batch."""
    existing = (
        supabase.table("inventory_container_imports")
        .select(
            "container_key,container_no,status,shipped_date,"
            "expected_arrival_date,department,category,brand,material,color,size"
        )
        .eq("container_key", container_key)
        .execute().data or []
    )
    if not existing:
        raise ValueError("未找到货柜记录")
    if any(
        str(row.get("status") or "") not in {"未到货", "在途", "延迟", "已到柜"}
        for row in existing
    ):
        raise ValueError("货柜已入库或取消，不能追加明细")

    cleaned_df = normalize_container_rows(df)
    if cleaned_df.empty:
        return []
    if set(cleaned_df["货柜记录ID"].astype(str)) != {str(container_key)}:
        raise ValueError("追加明细必须属于当前货柜")
    current_keys = {_container_item_key(row) for row in existing}
    new_keys = [_container_item_key(row) for row in _container_records(cleaned_df)]
    if len(set(new_keys)) != len(new_keys) or current_keys.intersection(new_keys):
        raise ValueError("货柜中已存在相同 SKU 明细")

    records = _container_records(cleaned_df)
    inserted = (
        supabase.table("inventory_container_imports")
        .insert(records).execute().data or []
    )
    first = existing[0]
    try:
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": first.get("container_no"),
            "event_type": "明细补充",
            "effective_date": datetime.now(
                ZoneInfo("America/New_York")
            ).date().isoformat(),
            "previous_status": first.get("status"),
            "new_status": first.get("status"),
            "operated_by": operated_by,
            "note": f"新增正式 SKU 货柜明细 {len(inserted)} 行",
        }).execute()
    except Exception:
        inserted_ids = [row.get("id") for row in inserted if row.get("id")]
        if inserted_ids:
            (
                supabase.table("inventory_container_imports")
                .delete().in_("id", inserted_ids).execute()
            )
        raise
    return inserted


def _container_records(cleaned_df):
    return [{
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
    } for row in cleaned_df.to_dict("records")]


def _container_item_key(row):
    return tuple(str(row.get(column) or "").strip().casefold() for column in (
        "department", "category", "brand", "material", "color", "size"
    ))
