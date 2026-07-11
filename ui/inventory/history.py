from db.inventory import load_inventory_movements
from db.inventory.sku import load_sku_imports
from ui.inventory.history_batches import (
    add_movement_batch_key,
    add_sku_batch_key,
    build_movement_batches,
    render_batch_selector,
)
from ui.inventory.history_tables import (
    render_movement_table,
    render_sku_import_table,
)


def render_selected_sku_import(dated_sku_import_df, selected_batch):
    dated_sku_import_df = add_sku_batch_key(dated_sku_import_df)
    render_sku_import_table(dated_sku_import_df[dated_sku_import_df["batch_key"] == selected_batch])


def render_selected_movement(dated_movement_df, selected_batch):
    dated_movement_df = add_movement_batch_key(dated_movement_df)
    render_movement_table(dated_movement_df[dated_movement_df["batch_key"] == selected_batch])


def render_inventory_history(supabase, department, category):
    movement_df = load_inventory_movements(supabase, department, "", limit=500)
    sku_import_df = load_sku_imports(supabase, department, "", limit=500)
    batch_df = build_movement_batches(movement_df, sku_import_df)
    selected_batch = render_batch_selector(batch_df)
    if not selected_batch:
        return

    selected_batch_df = batch_df[batch_df["batch_key"] == selected_batch]
    selected_type = selected_batch_df.iloc[0]["类型"] if not selected_batch_df.empty else ""
    if selected_type == "新增 SKU":
        render_selected_sku_import(sku_import_df, selected_batch)
        return

    render_selected_movement(movement_df, selected_batch)
