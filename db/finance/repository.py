import pandas as pd


PAGE_SIZE = 1000
ITEM_FIELDS = "department,category,brand,material,color,size"


def load_inventory_finance_month(supabase, start_date, end_date):
    inbound_rows = _fetch_pages(
        lambda start, end: (
            supabase.table("inventory_cost_lots")
            .select(
                "id,received_quantity,unit_cost,source_type,movement_date,"
                "reversed_at,"
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
                "id,quantity,unit_cost,source_type,reversed_at,"
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
        "date", "direction", "department", "category", "brand", "material",
        "color", "size", "quantity", "unit_cost", "amount", "source_type",
        "missing_cost",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    normalized = pd.json_normalize(rows, sep=".")
    relation_prefix = f"{relation}."
    result = pd.DataFrame({
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
