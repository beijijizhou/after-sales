import pandas as pd


PAGE_SIZE = 1000
ITEM_FIELDS = "department,category,brand,material,color,size"


def load_inventory_finance_month(supabase, start_date, end_date):
    inbound_rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_lots")
            .select(
                "id,inbound_movement_id,batch_id,received_quantity,unit_cost,"
                "source_type,movement_date,created_at,reversed_at,"
                "inventory_items!"
                "inventory_cost_lots_inventory_item_id_fkey!inner"
                f"({ITEM_FIELDS})"
            )
            .is_("reversed_at", "null")
            .in_("source_type", ["bulk", "transfer"])
            .gte("movement_date", start_date.isoformat())
            .lt("movement_date", end_date.isoformat())
            .order("id")
            .range(start, end)
            .execute()
            .data
        )
    )
    outbound_rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_allocations")
            .select(
                "id,quantity,unit_cost,source_type,created_at,reversed_at,"
                "inventory_movements!"
                "inventory_cost_allocations_outbound_movement_id_fkey!inner"
                "(movement_date,department,category,brand,material,color,size)"
            )
            .is_("reversed_at", "null")
            .gte("inventory_movements.movement_date", start_date.isoformat())
            .lt("inventory_movements.movement_date", end_date.isoformat())
            .order("id")
            .range(start, end)
            .execute()
            .data
        )
    )
    inbound = _normalize_cost_rows(
        inbound_rows,
        "inventory_items",
        "received_quantity",
        "入库",
        date_column="movement_date",
    )
    outbound = _normalize_cost_rows(
        outbound_rows,
        "inventory_movements",
        "quantity",
        "出库",
        date_column="inventory_movements.movement_date",
    )
    return pd.concat([inbound, outbound], ignore_index=True)


def load_inventory_value_snapshot(supabase):
    rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_source_summary")
            .select(
                "inventory_item_id,department,category,brand,material,color,"
                "size,inventory_quantity,tracked_quantity,"
                "regular_inventory_value,transfer_inventory_value,"
                "missing_cost_quantity"
            )
            .order("inventory_item_id")
            .range(start, end)
            .execute()
            .data
        )
    )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    numeric_columns = [
        "inventory_quantity", "tracked_quantity",
        "regular_inventory_value", "transfer_inventory_value",
        "missing_cost_quantity",
    ]
    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0)
    result["inventory_value"] = (
        result["regular_inventory_value"]
        + result["transfer_inventory_value"]
    )
    return result


def load_missing_inventory_cost_lots(supabase):
    rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_lots")
            .select(
                "id,inbound_movement_id,batch_id,received_quantity,"
                "remaining_quantity,unit_cost,source_type,movement_date,"
                "created_at,reversed_at,inventory_items!"
                "inventory_cost_lots_inventory_item_id_fkey!inner"
                f"({ITEM_FIELDS})"
            )
            .is_("reversed_at", "null")
            .is_("unit_cost", "null")
            .order("movement_date", desc=True)
            .order("id")
            .range(start, end)
            .execute()
            .data
        )
    )
    return _normalize_cost_rows(
        rows,
        "inventory_items",
        "received_quantity",
        "入库",
        date_column="movement_date",
    )


def load_container_finance_month(supabase, start_date, end_date):
    rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_container_imports")
            .select(
                "id,container_key,container_no,shipped_date,"
                "expected_arrival_date,actual_arrival_date,department,category,"
                "brand,material,color,size,quantity,unit_cost,status,note"
            )
            .gte("expected_arrival_date", start_date.isoformat())
            .lt("expected_arrival_date", end_date.isoformat())
            .order("id")
            .range(start, end)
            .execute()
            .data
        )
    )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["quantity"] = pd.to_numeric(
        result["quantity"], errors="coerce"
    ).fillna(0)
    result["unit_cost"] = pd.to_numeric(
        result["unit_cost"], errors="coerce"
    )
    result["amount"] = result["quantity"] * result["unit_cost"].fillna(0)
    result["missing_cost"] = result["unit_cost"].isna() | (
        result["unit_cost"] <= 0
    )
    return result


def update_inbound_lot_cost(supabase, cost_lot_id, unit_cost):
    unit_cost = float(unit_cost)
    if unit_cost <= 0:
        raise ValueError("批次成本必须大于 0")

    response = (
        supabase.table("inventory_cost_lots")
        .select("id,inbound_movement_id,reversed_at")
        .eq("id", cost_lot_id)
        .single()
        .execute()
    )
    lot = response.data
    if not lot or lot.get("reversed_at"):
        raise ValueError("找不到有效的入库成本批次")

    (
        supabase.table("inventory_cost_lots")
        .update({"unit_cost": unit_cost})
        .eq("id", cost_lot_id)
        .execute()
    )
    (
        supabase.table("inventory_cost_allocations")
        .update({"unit_cost": unit_cost})
        .eq("cost_lot_id", cost_lot_id)
        .is_("reversed_at", "null")
        .execute()
    )
    movement_id = lot.get("inbound_movement_id")
    if movement_id:
        (
            supabase.table("inventory_movements")
            .update({"unit_cost": unit_cost, "成本": unit_cost})
            .eq("id", movement_id)
            .execute()
        )
    return True


def _fetch_pages(fetch_page):
    rows = []
    offset = 0
    while True:
        page = fetch_page(offset, offset + PAGE_SIZE - 1)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _normalize_cost_rows(
    rows, relation, quantity_column, direction, date_column
):
    columns = [
        "record_id", "movement_id", "batch_id", "recorded_at",
        "date", "direction", "department",
        "category", "brand", "material", "color", "size", "quantity",
        "unit_cost", "amount", "source_type", "missing_cost",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    normalized = pd.json_normalize(rows, sep=".")
    relation_prefix = f"{relation}."
    result = pd.DataFrame({
        "record_id": normalized["id"],
        "movement_id": normalized.get("inbound_movement_id"),
        "batch_id": normalized.get("batch_id"),
        "date": normalized[date_column],
        "direction": direction,
        "department": normalized[f"{relation_prefix}department"],
        "category": normalized[f"{relation_prefix}category"],
        "brand": normalized[f"{relation_prefix}brand"],
        "material": normalized[f"{relation_prefix}material"],
        "color": normalized[f"{relation_prefix}color"],
        "size": normalized[f"{relation_prefix}size"],
        "quantity": normalized[quantity_column],
        "unit_cost": normalized["unit_cost"],
        "source_type": normalized["source_type"],
    })
    if "created_at" in normalized:
        result["recorded_at"] = pd.to_datetime(
            normalized["created_at"], errors="coerce", utc=True
        ).dt.tz_convert("America/New_York")
    else:
        result["recorded_at"] = pd.to_datetime(
            result["date"], errors="coerce"
        )
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.date
    result["quantity"] = pd.to_numeric(
        result["quantity"], errors="coerce"
    ).fillna(0)
    result["unit_cost"] = pd.to_numeric(
        result["unit_cost"], errors="coerce"
    )
    result["amount"] = result["quantity"] * result["unit_cost"].fillna(0)
    result["missing_cost"] = result["unit_cost"].isna()
    return result[columns]
