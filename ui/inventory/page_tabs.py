import streamlit as st

from ui.inventory.history.history import render_inventory_history
from ui.inventory.i18n import t
from ui.inventory.operations.forms import (
    render_adjust_form,
    render_inventory_unit_calculator,
    render_new_sku_form,
)
from ui.inventory.operations.outbound import render_daily_outbound
from ui.inventory.operations.sku_editor import (
    render_sku_catalog,
    render_sku_editor,
)
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
    can_view_cost, history_data, movement_types, filter_title,
):
    tab_names = [
        t("库存明细"), t("点货预测"), t("仓库每日出货及历史"),
        t("临时出入库及历史"), t("撤销"), t("SKU 管理"),
    ]
    if can_view_cost:
        tab_names.append(t("库存成本"))
    tabs = st.tabs(tab_names)

    with tabs[0]:
        if can_edit and not category:
            st.info(t("全部品类为汇总视图，请选择具体品类后直接编辑库存明细"))
        render_inventory_table(
            supabase, department, category, inventory_df, inventory_date,
            can_edit and bool(category) and selected_date == current_date,
            visible_sizes, filter_title,
        )
        render_inventory_metrics(inventory_df)
        render_black_white_color_summary(
            category, inventory_df, visible_sizes, filter_title
        )

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
        if can_edit:
            operation_category = _select_operation_category(
                category, raw_df, "daily_outbound_category"
            )
            if operation_category:
                render_daily_outbound(
                    supabase, department, operation_category
                )
                st.divider()
        _render_history(
            supabase, department, "daily", history_data, visible_sizes,
            movement_types,
        )

    with tabs[3]:
        if can_edit:
            operation_category = _select_operation_category(
                category, raw_df, "temporary_movement_category"
            )
            if operation_category:
                operation_inventory_df = inventory_df[
                    inventory_df["品类"] == operation_category
                ].reset_index(drop=True)
                render_inventory_unit_calculator()
                render_adjust_form(
                    supabase, department, operation_category,
                    operation_inventory_df,
                )
                st.divider()
        _render_history(
            supabase, department, "regular", history_data, visible_sizes,
            movement_types,
        )

    with tabs[4]:
        _render_history(
            supabase, department, "undo", history_data, visible_sizes,
            movement_types,
        )

    with tabs[5]:
        if can_edit:
            operation_category = _select_operation_category(
                category, raw_df, "sku_management_category"
            )
            operation_raw_df = raw_df[
                raw_df["category"] == operation_category
            ].reset_index(drop=True) if operation_category else raw_df.iloc[0:0]
            current_tab, create_tab, edit_tab = st.tabs([
                t("现有 SKU"), t("新增 SKU"), t("修改 SKU"),
            ])
            with current_tab:
                render_sku_catalog(operation_raw_df)
            with create_tab:
                if operation_category:
                    operation_inventory_df = inventory_df[
                        inventory_df["品类"] == operation_category
                    ].reset_index(drop=True)
                    render_new_sku_form(
                        supabase, department, operation_category,
                        operation_inventory_df,
                    )
            with edit_tab:
                render_sku_editor(
                    supabase, department, operation_raw_df
                )
            st.divider()
        else:
            render_sku_catalog(raw_df)
            st.divider()
        _render_history(
            supabase, department, "sku", history_data, visible_sizes,
            movement_types,
        )

    if can_view_cost:
        with tabs[6]:
            render_inventory_cost_summary(
                supabase, department, category, current_cost_df, raw_df
            )


def _render_history(
    supabase, department, mode, history_data, visible_sizes, movement_types
):
    render_inventory_history(
        supabase, department, mode, history_data=history_data,
        visible_sizes=visible_sizes,
        movement_types=movement_types,
    )


def _select_operation_category(category, raw_df, key):
    if category:
        return category
    if raw_df.empty or "category" not in raw_df.columns:
        st.info(t("当前没有可操作的库存品类"))
        return ""
    category_order = {value: index for index, value in enumerate([
        "黑白短袖", "彩色短袖", "卫衣",
    ])}
    options = sorted({
        str(value).strip() for value in raw_df["category"].dropna()
        if str(value).strip()
    }, key=lambda value: (category_order.get(value, 99), value))
    if not options:
        st.info(t("当前没有可操作的库存品类"))
        return ""
    st.caption(t("当前查看全部品类，请选择本次库存操作的目标品类"))
    return st.selectbox(t("操作品类"), options, key=key, format_func=t)
