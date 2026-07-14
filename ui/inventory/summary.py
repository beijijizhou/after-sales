from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    build_inventory_snapshot,
    build_inventory_table,
    get_inventory_last_updated,
    load_inventory_items,
    load_inventory_movements,
    load_inventory_snapshot,
)
from db.inventory.sku import load_sku_imports
from ui.inventory.forms import (
    render_adjust_form,
    render_new_sku_form,
)
from ui.inventory.consumption import (
    render_black_white_color_summary,
    render_consumption_model,
    render_consumption_planning_inputs,
    render_reorder_forecast,
)
from ui.inventory.calculator import render_inventory_unit_calculator
from ui.inventory.controls import (
    render_category_selector,
    render_department_selector,
    render_inventory_date_selector,
    render_setup_help,
)
from ui.inventory.history import load_inventory_history_data, render_inventory_history
from ui.inventory.i18n import render_language_selector, t
from ui.inventory.outbound import render_daily_outbound
from ui.inventory.table_filters import render_inventory_table_filters
from ui.inventory.table_editor import render_inventory_table_editor
from utils.auth import has_permission


def render_inventory_metrics(inventory_df):
    table_total = int(inventory_df["总库存"].sum())
    color_count = inventory_df["颜色"].nunique() if "颜色" in inventory_df.columns else 0

    col1, col2 = st.columns(2)
    col1.metric(t("当前表总库存"), table_total)
    col2.metric(t("当前表颜色数"), color_count)


def render_inventory_table(
    supabase, department, category, inventory_df, inventory_date, editable
):
    title_category = category or t("全部品类")
    st.subheader(f"{title_category} {t('库存明细')}")
    current_date = datetime.now(ZoneInfo("America/New_York")).date()

    col1, col2 = st.columns(2)
    col1.metric(t("当前日期"), current_date.isoformat())
    col2.metric(t("库存日期"), inventory_date.isoformat())
    display_df = render_inventory_table_filters(inventory_df, category)

    column_config = {
        "总库存": st.column_config.NumberColumn(t("总库存（全部尺码）"), format="%d"),
        "品类": st.column_config.TextColumn(t("品类")),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质")),
        "颜色": st.column_config.TextColumn(t("颜色")),
        **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
    }
    if "成本" in inventory_df.columns:
        column_config["成本"] = st.column_config.NumberColumn(t("成本"), format="%.2f")

    table_height = min(max((len(display_df) + 1) * 35 + 8, 220), 900)
    if editable:
        render_inventory_table_editor(
            supabase,
            department,
            category,
            display_df,
            column_config,
            table_height,
        )
    else:
        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            column_config=column_config,
            height=table_height,
        )


def render_inventory_summary(supabase):
    st.title(t("库存"))
    render_language_selector()
    saved_message = st.session_state.pop("inventory_saved_message", None)
    if saved_message:
        st.success(saved_message)
    department = render_department_selector(supabase)
    category = render_category_selector(department)
    st.session_state["inventory_today"] = datetime.now(ZoneInfo("America/New_York")).date()
    selected_date = render_inventory_date_selector()

    try:
        raw_df = load_inventory_items(supabase, department, category)
        try:
            snapshot_df = load_inventory_snapshot(supabase, department, category, selected_date)
        except Exception:
            snapshot_df = raw_df.iloc[0:0]

        has_saved_snapshot = not snapshot_df.empty
        if snapshot_df.empty:
            movement_df = load_inventory_movements(supabase, department, category, limit=10000)
            sku_import_df = load_sku_imports(supabase, department, category, limit=10000)
            snapshot_df = build_inventory_snapshot(raw_df, movement_df, sku_import_df, selected_date)

        inventory_df = build_inventory_table(snapshot_df, category, include_cost=has_permission("can_view_cost"))
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
        tab_names = [
            t("库存明细"),
            t("点货预测"),
            t("每日出库及历史"),
            t("日常出入库及历史"),
            t("撤销"),
            t("新建 SKU"),
        ]
        tabs = st.tabs(tab_names)

        with tabs[0]:
            render_inventory_table(
                supabase, department, category, inventory_df, inventory_date,
                can_edit and selected_date == current_date,
            )
            render_inventory_metrics(inventory_df)
            render_black_white_color_summary(category, inventory_df)

        with tabs[1]:
            order_quantity, arrival_date, buffer_days = (
                render_consumption_planning_inputs(category)
            )
            render_consumption_model(supabase, category, order_quantity)
            render_reorder_forecast(
                supabase, category, inventory_df, order_quantity,
                arrival_date, buffer_days, inventory_date,
            )

        with tabs[2]:
            if can_edit:
                render_daily_outbound(supabase, department, category)
                st.divider()
            render_inventory_history(
                supabase, department, "daily", history_data=history_data
            )

        with tabs[3]:
            if can_edit:
                render_inventory_unit_calculator()
                render_adjust_form(supabase, department, category, inventory_df)
                st.divider()
            render_inventory_history(
                supabase, department, "regular", history_data=history_data
            )

        with tabs[4]:
            render_inventory_history(
                supabase, department, "undo", history_data=history_data
            )

        with tabs[5]:
            if can_edit:
                render_new_sku_form(supabase, department, category, inventory_df)
                st.divider()
            render_inventory_history(
                supabase, department, "sku", history_data=history_data
            )

    except Exception as e:
        st.error(f"{t('库存数据加载失败')}: {e}")
        render_setup_help()
