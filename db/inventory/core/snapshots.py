import pandas as pd


INVENTORY_KEY_COLUMNS = [
    "department", "category", "brand", "material", "color", "size",
]


def filter_snapshot_to_active_skus(snapshot_df, active_inventory_df):
    """Keep current active SKU identities while preserving snapshot values."""
    snapshot = pd.DataFrame(snapshot_df).copy()
    active = pd.DataFrame(active_inventory_df).copy()
    if snapshot.empty or active.empty:
        return snapshot.iloc[0:0].copy()
    keys = [
        column for column in INVENTORY_KEY_COLUMNS
        if column in snapshot.columns and column in active.columns
    ]
    if not keys:
        return snapshot.iloc[0:0].copy()
    for frame in (snapshot, active):
        for column in keys:
            frame[column] = frame[column].fillna("").astype(str).str.strip()
        if "size" in keys:
            frame["size"] = frame["size"].str.upper()
    active_keys = active[keys].drop_duplicates()
    return snapshot.merge(
        active_keys, on=keys, how="inner", validate="many_to_one"
    )


def load_inventory_snapshot(supabase, department, category, snapshot_date):
    response = (
        supabase
        .rpc(
            "get_inventory_snapshot",
            {
                "p_department": department,
                "p_category": category,
                "p_snapshot_date": snapshot_date.isoformat(),
            }
        )
        .execute()
    )
    return pd.DataFrame(response.data)


def create_inventory_snapshot(supabase, department, category, snapshot_date):
    response = (
        supabase
        .rpc(
            "create_inventory_snapshot",
            {
                "p_department": department,
                "p_category": category,
                "p_snapshot_date": snapshot_date.isoformat(),
            }
        )
        .execute()
    )
    return response.data


def normalize_inventory_key_columns(df):
    normalized_df = df.copy()
    for column in ["department", "category", "brand", "material", "color", "size"]:
        if column not in normalized_df.columns:
            normalized_df[column] = ""
        normalized_df[column] = normalized_df[column].fillna("").astype(str).str.strip()
    normalized_df["size"] = normalized_df["size"].str.upper()
    return normalized_df


def subtract_future_inventory_change(snapshot_df, change_df, date_column, quantity_column, selected_date):
    if change_df.empty or date_column not in change_df.columns or quantity_column not in change_df.columns:
        return snapshot_df

    key_columns = ["department", "category", "brand", "material", "color", "size"]
    future_df = normalize_inventory_key_columns(change_df)
    future_df[date_column] = pd.to_datetime(future_df[date_column], errors="coerce").dt.date
    future_df[quantity_column] = pd.to_numeric(future_df[quantity_column], errors="coerce").fillna(0)
    future_df = future_df[future_df[date_column] > selected_date]
    if future_df.empty:
        return snapshot_df

    future_df = (
        future_df
        .groupby(key_columns, as_index=False)[quantity_column]
        .sum()
        .rename(columns={quantity_column: "_future_quantity_change"})
    )
    snapshot_df = snapshot_df.merge(future_df, on=key_columns, how="left")
    snapshot_df["_future_quantity_change"] = snapshot_df["_future_quantity_change"].fillna(0)
    snapshot_df["quantity"] = snapshot_df["quantity"] - snapshot_df["_future_quantity_change"]
    return snapshot_df.drop(columns=["_future_quantity_change"])


def build_inventory_snapshot(current_df, movement_df, sku_import_df, selected_date):
    if current_df.empty:
        return current_df

    snapshot_df = normalize_inventory_key_columns(current_df)
    if "unit_cost" not in snapshot_df.columns:
        snapshot_df["unit_cost"] = 0
    if "updated_at" not in snapshot_df.columns:
        snapshot_df["updated_at"] = pd.NA
    snapshot_df["quantity"] = pd.to_numeric(snapshot_df["quantity"], errors="coerce").fillna(0)

    snapshot_df = subtract_future_inventory_change(
        snapshot_df,
        movement_df,
        "movement_date",
        "quantity_change",
        selected_date,
    )
    snapshot_df = subtract_future_inventory_change(
        snapshot_df,
        sku_import_df,
        "import_date",
        "initial_quantity",
        selected_date,
    )
    snapshot_df["quantity"] = snapshot_df["quantity"].clip(lower=0).round().astype(int)
    return snapshot_df
