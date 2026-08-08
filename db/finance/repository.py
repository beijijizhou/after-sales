from datetime import date, timedelta

import pandas as pd


PAGE_SIZE = 1000
ITEM_FIELDS = "department,category,brand,material,color,size"
FINANCE_COLUMNS = [
    "record_id", "movement_id", "batch_id", "recorded_at",
    "date", "direction", "department", "category", "brand",
    "material", "color", "size", "quantity", "unit_cost",
    "amount", "source_type", "missing_cost",
]


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
    consumables = load_consumable_finance_month(
        supabase, start_date, end_date
    )
    return pd.concat(
        [inbound, outbound, consumables], ignore_index=True
    )


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
        result = pd.DataFrame()
    numeric_columns = [
        "inventory_quantity", "tracked_quantity",
        "regular_inventory_value", "transfer_inventory_value",
        "missing_cost_quantity",
    ]
    if not result.empty:
        for column in numeric_columns:
            result[column] = pd.to_numeric(
                result[column], errors="coerce"
            ).fillna(0)
        result["inventory_value"] = (
            result["regular_inventory_value"]
            + result["transfer_inventory_value"]
        )
    consumables = load_consumable_value_snapshot(supabase)
    return pd.concat([result, consumables], ignore_index=True)


def load_consumable_finance_month(supabase, start_date, end_date):
    departments, items, batches, movements = _load_consumable_frames(
        supabase, end_date=end_date
    )
    return normalize_consumable_finance_rows(
        departments, items, batches, movements, start_date, end_date
    )


def load_consumable_value_snapshot(supabase):
    departments, items, batches, movements = _load_consumable_frames(
        supabase
    )
    columns = [
        "department", "category", "brand", "material", "color", "size",
        "inventory_quantity", "tracked_quantity",
        "regular_inventory_value", "transfer_inventory_value",
        "missing_cost_quantity", "inventory_value",
    ]
    if items.empty:
        return pd.DataFrame(columns=columns)
    active = _active_consumable_movements(batches, movements)
    latest_costs = _latest_consumable_costs(active)
    data = items.copy()
    department_codes = (
        departments.set_index("id")["code"].to_dict()
        if not departments.empty else {}
    )
    data["department"] = data["department_id"].map(department_codes)
    data["brand"] = data["brand"].fillna("")
    data["material"] = data["category"].fillna("")
    data["color"] = data["name"].fillna("")
    data["size"] = data["specification"].fillna("")
    data["category"] = "DTF耗材"
    data["inventory_quantity"] = pd.to_numeric(
        data["current_quantity"], errors="coerce"
    ).fillna(0)
    data["unit_cost"] = data["id"].astype(str).map(latest_costs)
    data["tracked_quantity"] = data["inventory_quantity"].where(
        data["unit_cost"].notna(), 0
    )
    data["regular_inventory_value"] = (
        data["inventory_quantity"] * data["unit_cost"].fillna(0)
    )
    data["transfer_inventory_value"] = 0.0
    data["missing_cost_quantity"] = data["inventory_quantity"].where(
        data["unit_cost"].isna(), 0
    )
    data["inventory_value"] = data["regular_inventory_value"]
    return data[columns]


def normalize_consumable_finance_rows(
    departments, items, batches, movements, start_date, end_date,
):
    if items.empty or batches.empty or movements.empty:
        return pd.DataFrame(columns=FINANCE_COLUMNS)
    active = _active_consumable_movements(batches, movements)
    if active.empty:
        return pd.DataFrame(columns=FINANCE_COLUMNS)
    item_source = items.rename(columns={
        "category": "item_category", "brand": "item_brand",
        "name": "item_name", "specification": "item_specification",
    })
    data = active.merge(
        item_source,
        left_on="item_id",
        right_on="id",
        how="left",
        suffixes=("", "_item"),
    )
    data = data.merge(
        departments[["id", "code"]].rename(
            columns={"id": "department_id", "code": "department"}
        ),
        on="department_id",
        how="left",
    )
    data["date"] = pd.to_datetime(
        data["movement_date"], errors="coerce"
    ).dt.date
    data = data[
        (data["date"] >= start_date) & (data["date"] < end_date)
    ].copy()
    if data.empty:
        return pd.DataFrame(columns=FINANCE_COLUMNS)
    latest_costs = _latest_consumable_costs(active)
    data["quantity"] = pd.to_numeric(
        data["quantity_change"], errors="coerce"
    ).abs().fillna(0)
    data["direction"] = data["quantity_change"].apply(
        lambda value: "入库" if float(value) > 0 else "出库"
    )
    explicit_cost = pd.to_numeric(data["unit_cost"], errors="coerce")
    inferred_cost = data["item_id"].astype(str).map(latest_costs)
    data["unit_cost"] = explicit_cost.where(
        explicit_cost.notna() | (data["direction"] == "入库"),
        inferred_cost,
    )
    data["amount"] = data["quantity"] * data["unit_cost"].fillna(0)
    data["missing_cost"] = data["unit_cost"].isna()
    data["record_id"] = data["id"].astype(str)
    data["movement_id"] = data["record_id"]
    data["recorded_at"] = pd.to_datetime(
        data["created_at"], errors="coerce", utc=True
    ).dt.tz_convert("America/New_York")
    data["category"] = "DTF耗材"
    data["brand"] = data["item_brand"].fillna("")
    data["material"] = data["item_category"].fillna("")
    data["color"] = data["item_name"].fillna("")
    data["size"] = data["item_specification"].fillna("")
    data["source_type"] = "consumable_" + data[
        "movement_type"
    ].fillna("adjustment").astype(str)
    return data[FINANCE_COLUMNS].reset_index(drop=True)


def _load_consumable_frames(supabase, end_date=None):
    departments = pd.DataFrame(_fetch_pages(
        lambda start, end: supabase.table("inventory_departments")
        .select("id,code").order("id").range(start, end).execute().data
    ))
    item_columns = (
        "id,department_id,category,name,specification,brand,base_unit,"
        "package_unit,units_per_package,current_quantity"
    )
    items = pd.DataFrame(_fetch_pages(
        lambda start, end: supabase.table("consumable_items")
        .select(item_columns).order("id").range(start, end).execute().data
    ))
    batch_columns = (
        "id,department_id,movement_type,movement_date,created_at,"
        "reversal_of_batch_id"
    )
    def fetch_batches(start, end):
        query = supabase.table("consumable_movement_batches").select(
            batch_columns
        )
        return query.order("id").range(start, end).execute().data
    batches = pd.DataFrame(_fetch_pages(fetch_batches))
    movement_columns = (
        "id,batch_id,item_id,movement_date,quantity_change,unit_cost,"
        "created_at"
    )
    def fetch_movements(start, end):
        query = supabase.table("consumable_movements").select(
            movement_columns
        )
        if end_date:
            query = query.lt("movement_date", end_date.isoformat())
        return query.order("id").range(start, end).execute().data
    movements = pd.DataFrame(_fetch_pages(fetch_movements))
    item_defaults = {
        "id": "", "department_id": "", "category": "", "name": "",
        "specification": "", "brand": "", "current_quantity": 0,
    }
    for column, default in item_defaults.items():
        if column not in items:
            items[column] = default
    return departments, items, batches, movements


def _active_consumable_movements(batches, movements):
    if batches.empty or movements.empty:
        return pd.DataFrame()
    reversed_ids = set(
        batches.get("reversal_of_batch_id", pd.Series(dtype=object))
        .dropna().astype(str)
    )
    reversal_ids = set(
        batches.loc[
            batches.get("movement_type", pd.Series(index=batches.index))
            == "reversal", "id"
        ].astype(str)
    )
    excluded = reversed_ids | reversal_ids
    active_batches = batches[
        ~batches["id"].astype(str).isin(excluded)
    ].copy()
    return movements.merge(
        active_batches[["id", "department_id", "movement_type"]].rename(
            columns={"id": "active_batch_id"}
        ),
        left_on="batch_id",
        right_on="active_batch_id",
        how="inner",
    )


def _latest_consumable_costs(movements):
    if movements.empty:
        return {}
    priced = movements.copy()
    priced["unit_cost"] = pd.to_numeric(
        priced["unit_cost"], errors="coerce"
    )
    priced = priced[priced["unit_cost"].notna()]
    if priced.empty:
        return {}
    priced["_sort_date"] = pd.to_datetime(
        priced["movement_date"], errors="coerce"
    )
    priced["_sort_created"] = pd.to_datetime(
        priced["created_at"], errors="coerce", utc=True
    )
    return (
        priced.sort_values(["_sort_date", "_sort_created"])
        .drop_duplicates("item_id", keep="last")
        .assign(item_id=lambda frame: frame["item_id"].astype(str))
        .set_index("item_id")["unit_cost"]
        .to_dict()
    )


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
    inventory = _normalize_cost_rows(
        rows,
        "inventory_items",
        "received_quantity",
        "入库",
        date_column="movement_date",
    )
    consumables = load_missing_consumable_cost_movements(supabase)
    return pd.concat([inventory, consumables], ignore_index=True)


def load_missing_consumable_cost_movements(supabase):
    departments, items, batches, movements = _load_consumable_frames(
        supabase
    )
    rows = normalize_consumable_finance_rows(
        departments,
        items,
        batches,
        movements,
        date(2000, 1, 1),
        date.today() + timedelta(days=1),
    )
    if rows.empty:
        return rows
    return rows[
        (rows["direction"] == "入库") & rows["missing_cost"]
    ].reset_index(drop=True)


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


def update_consumable_movement_cost(supabase, movement_id, unit_cost):
    unit_cost = float(unit_cost)
    if unit_cost <= 0:
        raise ValueError("耗材单位成本必须大于 0")
    response = (
        supabase.table("consumable_movements")
        .select("id,quantity_change,reversal_of_movement_id")
        .eq("id", movement_id)
        .single()
        .execute()
    )
    movement = response.data
    if not movement or movement.get("reversal_of_movement_id"):
        raise ValueError("找不到有效的耗材入库记录")
    if float(movement.get("quantity_change") or 0) <= 0:
        raise ValueError("只有耗材入库记录可以填写单位成本")
    (
        supabase.table("consumable_movements")
        .update({"unit_cost": unit_cost})
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
