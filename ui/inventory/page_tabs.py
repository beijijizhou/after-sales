import streamlit as st

from ui.inventory.history.history import render_inventory_history
from ui.inventory.i18n import t
from ui.inventory.operations.forms import (
    render_adjust_form,
    render_inventory_unit_calculator,
    render_new_sku_form,
)
from ui.inventory.operations.outbound import render_daily_outbound
from ui.inventory.planning.consumption import (
    render_black_white_color_summary,
    render_consumption_model,
    render_consumption_planning_inputs,
    render_reorder_forecast,
)
from ui.inventory.stock.cost_summary import render_inventory_cost_summary
from ui.inventory.stock.table import (
    render_inventory_metrics,
    render_inventory_table,
)


def render_inventory_tabs(
    supabase, department, category, inventory_df, raw_df, current_cost_df,
    inventory_date, selected_date, current_date, visible_sizes, can_edit,
    can_view_cost, history_data,
):
    tab_names = [
        t("库存明细"), t("点货预测"), t("每日出库及历史"),
        t("日常出入库及历史"), t("撤销"), t("新建 SKU"),
    ]
    if can_view_cost:
        tab_names.append(t("库存成本"))
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_inventory_table(
            supabase, department, category, inventory_df, inventory_date,
            can_edit and bool(category) and selected_date == current_date,
            visible_sizes,
        )
        render_inventory_metrics(inventory_df)
        render_black_white_color_summary(category, inventory_df, visible_sizes)

    with tabs[1]:
        order_quantity, arrival_date, buffer_days = (
            render_consumption_planning_inputs(category)
        )
        render_reorder_forecast(
            supabase, department, category, inventory_df, order_quantity,
            arrival_date, buffer_days, inventory_date, visible_sizes,
        )
        render_consumption_model(
            supabase, category, order_quantity, visible_sizes
        )

    with tabs[2]:
        if can_edit and category:
            render_daily_outbound(supabase, department, category)
            st.divider()
        elif can_edit:
            st.info(t("请先选择具体品类再进行库存操作"))
        _render_history(
            supabase, department, "daily", history_data, visible_sizes
        )

    with tabs[3]:
        if can_edit and category:
            render_inventory_unit_calculator()
            render_adjust_form(
                supabase, department, category, inventory_df
            )
            st.divider()
        elif can_edit:
            st.info(t("请先选择具体品类再进行库存操作"))
        _render_history(
            supabase, department, "regular", history_data, visible_sizes
        )

    with tabs[4]:
        _render_history(
            supabase, department, "undo", history_data, visible_sizes
        )

    with tabs[5]:
        if can_edit and category:
            render_new_sku_form(
                supabase, department, category, inventory_df
            )
            st.divider()
        elif can_edit:
            st.info(t("请先选择具体品类再进行库存操作"))
        _render_history(
            supabase, department, "sku", history_data, visible_sizes
        )

    if can_view_cost:
        with tabs[6]:
            render_inventory_cost_summary(
                supabase, department, category, current_cost_df, raw_df
            )


def _render_history(
    supabase, department, mode, history_data, visible_sizes
):
    render_inventory_history(
        supabase, department, mode, history_data=history_data,
        visible_sizes=visible_sizes,
    )
