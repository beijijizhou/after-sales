from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    build_inventory_snapshot,
    build_inventory_table,
    get_inventory_last_updated,
    load_inventory_dimensions,
    load_inventory_items,
    load_inventory_movements,
    load_inventory_snapshot,
)
from db.inventory.sku import load_sku_imports
from ui.inventory.history.history import (
    filter_inventory_history_data,
    load_inventory_history_data,
)
from ui.inventory.i18n import render_language_selector, t
from ui.inventory.page_tabs import render_inventory_tabs
from ui.inventory.shared import (
    build_inventory_filter_title,
    filter_inventory_rows,
    render_inventory_global_filters,
)
from utils.auth import has_permission


def render_inventory_summary(supabase):
    st.title(t("库存"))
    render_language_selector()
    saved_message = st.session_state.pop("inventory_saved_message", None)
    if saved_message:
        st.success(saved_message)
    try:
        dimensions_df = load_inventory_dimensions(supabase)
    except Exception as error:
        st.error(f"{t('库存数据加载失败')}: {error}")
        return
    (
        department, category, brands, materials, colors, selected_sizes,
        movement_types, selected_date,
    ) = (
        render_inventory_global_filters(dimensions_df)
    )
    visible_sizes = selected_sizes or SIZE_COLUMNS
    filter_title = build_inventory_filter_title(
        category, brands, materials, colors, selected_sizes
    )
    st.session_state["inventory_today"] = datetime.now(ZoneInfo("America/New_York")).date()

    try:
        raw_df = load_inventory_items(supabase, department, category)
        raw_df = filter_inventory_rows(
            raw_df, category, brands, materials, colors, selected_sizes
        )
        try:
            snapshot_df = load_inventory_snapshot(supabase, department, category, selected_date)
            snapshot_df = filter_inventory_rows(
                snapshot_df, category, brands, materials, colors,
                selected_sizes,
            )
        except Exception:
            snapshot_df = raw_df.iloc[0:0]

        has_saved_snapshot = not snapshot_df.empty
        if snapshot_df.empty:
            movement_df = load_inventory_movements(supabase, department, category, limit=10000)
            sku_import_df = load_sku_imports(supabase, department, category, limit=10000)
            movement_df = filter_inventory_rows(
                movement_df, category, brands, materials, colors,
                selected_sizes,
            )
            sku_import_df = filter_inventory_rows(
                sku_import_df, category, brands, materials, colors,
                selected_sizes,
            )
            snapshot_df = build_inventory_snapshot(raw_df, movement_df, sku_import_df, selected_date)

        can_view_cost = has_permission("can_view_cost")
        inventory_df = build_inventory_table(snapshot_df, category, include_cost=False)
        current_cost_df = (
            build_inventory_table(raw_df, category, include_cost=True)
            if can_view_cost else None
        )
        current_date = st.session_state["inventory_today"]
        inventory_date = (
            selected_date
            if selected_date < current_date
            else get_inventory_last_updated(raw_df) or selected_date
        )
        if inventory_df.empty:
            st.warning(t("暂无库存数据"))

        can_edit = has_permission("can_edit_inventory")
        history_data = load_inventory_history_data(supabase, department)
        history_data = filter_inventory_history_data(
            history_data, category, brands, materials, colors, selected_sizes
        )
        render_inventory_tabs(
            supabase, department, category, inventory_df, raw_df,
            current_cost_df, inventory_date, selected_date, current_date,
            visible_sizes, can_edit, can_view_cost, history_data,
            movement_types,
            filter_title,
        )

    except Exception as e:
        st.error(f"{t('库存数据加载失败')}: {e}")
