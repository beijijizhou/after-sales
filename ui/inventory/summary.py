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
    load_latest_inventory_movement_date,
    load_inventory_movements,
    load_inventory_snapshot,
)
from db.inventory.core.snapshots import (
    filter_snapshot_to_active_skus,
    should_use_saved_snapshot,
)
from db.inventory.sku import load_sku_imports
from ui.inventory.history.workflows.page import (
    filter_inventory_history_data,
    load_inventory_history_data,
)
from ui.inventory.history.core.filters import movement_type_options
from ui.inventory.i18n import get_language, render_language_selector, t
from ui.inventory.category_routing import (
    apply_phone_case_display_scope,
    exclude_consumable_dimensions,
)
from ui.inventory.operations.outbound_feedback import (
    render_saved_outbound_audit_feedback,
)
from ui.inventory.operations.outbound_i18n import TEXT as OUTBOUND_TEXT
from ui.inventory.operations.outbound_status import (
    clear_daily_outbound_backfill,
    render_colored_daily_consumption_alert,
    render_daily_outbound_alert,
    render_uv_daily_consumption_alert,
)
from ui.inventory.operations.pages import render_daily_outbound_operation
from ui.inventory.page_tabs import render_inventory_tabs
from ui.inventory.shared import (
    build_inventory_filter_title,
    filter_inventory_rows,
    render_inventory_activity_filters,
    render_inventory_dimension_filters,
)
from utils.auth import has_permission
from utils.daily_consumption import (
    ENTRY_MANUAL,
    inventory_daily_consumption_flow,
)


def render_inventory_summary(supabase):
    st.title(t("库存"))
    render_language_selector()
    saved_message = st.session_state.pop("inventory_saved_message", None)
    if saved_message:
        st.success(saved_message)
    render_saved_outbound_audit_feedback(
        OUTBOUND_TEXT[get_language()]
    )
    try:
        dimensions_df = load_inventory_dimensions(supabase)
    except Exception as error:
        st.error(f"{t('库存数据加载失败')}: {error}")
        return
    dimensions_df = exclude_consumable_dimensions(dimensions_df)
    (
        department, category, brands, materials, colors, selected_sizes,
    ) = render_inventory_dimension_filters(
        dimensions_df, key="inventory_global"
    )
    try:
        complete_history_data = load_inventory_history_data(
            supabase, department, limit=10000
        )
    except Exception as error:
        st.error(f"{t('库存数据加载失败')}: {error}")
        return
    movement_types, selected_date, _use_snapshot_date = (
        render_inventory_activity_filters(
            movement_type_options(complete_history_data[2]),
            key="inventory_global",
        )
    )
    visible_sizes = selected_sizes or (
        SIZE_COLUMNS if department == "DTF" else None
    )
    filter_title = build_inventory_filter_title(
        category, brands, materials, colors, selected_sizes
    )
    if department == "UV" and not category:
        filter_title = "UV 生产库存（不含手机壳）"
    can_edit = has_permission("can_edit_inventory")
    flow = inventory_daily_consumption_flow(department, category)
    if can_edit and flow:
        if flow.entry_source == ENTRY_MANUAL:
            render_daily_outbound_alert(supabase, department)
        elif flow.code == "colored_tshirts":
            render_colored_daily_consumption_alert(supabase)
        elif flow.code == "uv_production":
            render_uv_daily_consumption_alert(supabase)
    st.session_state["inventory_today"] = datetime.now(ZoneInfo("America/New_York")).date()

    try:
        complete_category_raw_df = load_inventory_items(
            supabase, department, category
        )
        complete_category_raw_df = apply_phone_case_display_scope(
            complete_category_raw_df, department, category
        )
        focused_outbound_date = st.session_state.get(
            "daily_outbound_focus_date"
        )
        if focused_outbound_date and flow and flow.entry_source == ENTRY_MANUAL:
            st.divider()
            title_column, action_column = st.columns([4, 1])
            title_column.subheader(
                f"补录仓库每日出货｜{focused_outbound_date:%Y-%m-%d}"
            )
            action_column.button(
                "返回库存",
                key="close_daily_outbound_backfill",
                width="stretch",
                on_click=clear_daily_outbound_backfill,
            )
            st.caption(
                "日期已经自动带入；核对各 SKU 数量后保存，系统会保留完整批次流水。"
            )
            render_daily_outbound_operation(
                supabase,
                department,
                category,
                complete_category_raw_df,
                can_edit,
            )
            return
        raw_df = filter_inventory_rows(
            complete_category_raw_df,
            category, brands, materials, colors, selected_sizes,
        )
        current_date = st.session_state["inventory_today"]
        if should_use_saved_snapshot(selected_date, current_date):
            try:
                snapshot_df = load_inventory_snapshot(
                    supabase, department, category, selected_date
                )
                snapshot_df = filter_snapshot_to_active_skus(
                    snapshot_df, complete_category_raw_df
                )
                snapshot_df = filter_inventory_rows(
                    snapshot_df, category, brands, materials, colors,
                    selected_sizes,
                )
            except Exception:
                snapshot_df = raw_df.iloc[0:0]
        else:
            snapshot_df = raw_df.copy()

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
            snapshot_df = filter_snapshot_to_active_skus(
                snapshot_df, complete_category_raw_df
            )

        can_view_cost = has_permission("can_view_cost")
        inventory_df = build_inventory_table(
            snapshot_df, category, include_cost=False, department=department
        )
        operation_inventory_df = build_inventory_table(
            complete_category_raw_df,
            category,
            include_cost=False,
            department=department,
        )
        current_cost_df = (
            build_inventory_table(
                raw_df, category, include_cost=True, department=department
            )
            if can_view_cost else None
        )
        # The as-of date describes the department ledger, not the current
        # display filters. Filtering a quiet SKU must not move the ledger back.
        latest_movement_date = load_latest_inventory_movement_date(
            supabase, department
        )
        inventory_date = (
            selected_date
            if selected_date < current_date
            else (
                latest_movement_date
                or get_inventory_last_updated(raw_df)
                or selected_date
            )
        )
        if inventory_df.empty:
            st.warning(t("暂无库存数据"))

        history_data = filter_inventory_history_data(
            complete_history_data,
            category, brands, materials, colors, selected_sizes,
        )
        history_filter_active = bool(
            brands or materials or colors or selected_sizes
        )
        render_inventory_tabs(
            supabase, department, category, inventory_df, raw_df,
            current_cost_df, inventory_date, selected_date, current_date,
            visible_sizes, can_edit, can_view_cost, history_data,
            movement_types,
            filter_title,
            undo_history_data=complete_history_data,
            operation_inventory_df=operation_inventory_df,
            operation_raw_df=complete_category_raw_df,
            history_filter_active=history_filter_active,
        )

    except Exception as e:
        st.error(f"{t('库存数据加载失败')}: {e}")
