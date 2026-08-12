"""Consumable movements normalized into the shared finance schema."""

import pandas as pd

from db.finance.repository import FINANCE_COLUMNS, _fetch_pages


def load_consumable_finance_month(supabase, start_date, end_date):
    departments, items, batches, movements = _load_consumable_frames(
        supabase, end_date=end_date
    )
    return normalize_consumable_finance_rows(
        departments, items, batches, movements, start_date, end_date
    )


def load_consumable_value_snapshot(supabase):
    departments, items, batches, movements = _load_consumable_frames(supabase)
    columns = [
        "department", "category", "brand", "material", "color", "size",
        "inventory_quantity", "tracked_quantity", "regular_inventory_value",
        "transfer_inventory_value", "missing_cost_quantity", "inventory_value",
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
        item_source, left_on="item_id", right_on="id", how="left",
        suffixes=("", "_item"),
    ).merge(
        departments[["id", "code"]].rename(
            columns={"id": "department_id", "code": "department"}
        ), on="department_id", how="left",
    )
    data["date"] = pd.to_datetime(
        data["movement_date"], errors="coerce"
    ).dt.date
    data = data[(data["date"] >= start_date) & (data["date"] < end_date)].copy()
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
        explicit_cost.notna() | (data["direction"] == "入库"), inferred_cost,
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


def load_consumable_frames(supabase, end_date=None):
    return _load_consumable_frames(supabase, end_date)


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
    batches = pd.DataFrame(_fetch_pages(
        lambda start, end: supabase.table("consumable_movement_batches")
        .select(batch_columns).order("id").range(start, end).execute().data
    ))
    movement_columns = (
        "id,batch_id,item_id,movement_date,quantity_change,unit_cost,created_at"
    )

    def fetch_movements(start, end):
        query = supabase.table("consumable_movements").select(movement_columns)
        if end_date:
            query = query.lt("movement_date", end_date.isoformat())
        return query.order("id").range(start, end).execute().data

    movements = pd.DataFrame(_fetch_pages(fetch_movements))
    defaults = {
        "id": "", "department_id": "", "category": "", "name": "",
        "specification": "", "brand": "", "current_quantity": 0,
    }
    for column, default in defaults.items():
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
    reversal_ids = set(batches.loc[
        batches.get("movement_type", pd.Series(index=batches.index)) == "reversal",
        "id",
    ].astype(str))
    active = batches[~batches["id"].astype(str).isin(reversed_ids | reversal_ids)]
    return movements.merge(
        active[["id", "department_id", "movement_type"]].rename(
            columns={"id": "active_batch_id"}
        ), left_on="batch_id", right_on="active_batch_id", how="inner",
    )


def _latest_consumable_costs(movements):
    if movements.empty:
        return {}
    priced = movements.copy()
    priced["unit_cost"] = pd.to_numeric(priced["unit_cost"], errors="coerce")
    priced = priced[priced["unit_cost"].notna()]
    if priced.empty:
        return {}
    priced["_sort_date"] = pd.to_datetime(priced["movement_date"], errors="coerce")
    priced["_sort_created"] = pd.to_datetime(
        priced["created_at"], errors="coerce", utc=True
    )
    return (
        priced.sort_values(["_sort_date", "_sort_created"])
        .drop_duplicates("item_id", keep="last")
        .assign(item_id=lambda frame: frame["item_id"].astype(str))
        .set_index("item_id")["unit_cost"].to_dict()
    )
