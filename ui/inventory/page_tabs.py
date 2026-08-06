import streamlit as st

from utils.auth import has_permission
from ui.inventory.history.history import (
    render_inventory_history,
    render_sku_operation_history,
)
from ui.inventory.i18n import t
from ui.inventory.operations.pages import (
    render_daily_outbound_operation,
    render_temporary_movement_operation,
)
from ui.inventory.planning.comparison import render_consumption_models
from ui.inventory.planning.comparison import render_uv_daily_deduction
from ui.inventory.planning.colored_consumption import (
    render_colored_daily_deduction,
)
from ui.inventory.planning.consumption import (
    render_consumption_planning_inputs,
    render_reorder_forecast,
)
from ui.inventory.stock.cost_summary import render_inventory_cost_summary
from ui.inventory.stock.incoming import render_incoming_inventory_forecast
from ui.inventory.stock.summary import render_black_white_color_summary
from ui.inventory.stock.table import (
    render_inventory_metrics,
    render_inventory_table,
    render_inventory_view_mode,
)
from ui.inventory.sku import render_sku_management
from ui.inventory.sku.initialization import (
    render_inventory_initialization,
)


def render_inventory_tabs(
    supabase, department, category, inventory_df, raw_df, current_cost_df,
    inventory_date, selected_date, current_date, visible_sizes, can_edit,
    can_view_cost, history_data, movement_types, filter_title,
    sku_filters=None,
    undo_history_data=None,
):
    tab_keys = inventory_tab_keys(
        department, can_view_cost=can_view_cost, category=category
    )
    tab_names = [t(name) for name in tab_keys]
    tabs = dict(zip(tab_keys, st.tabs(tab_names)))

    with tabs["库存明细"]:
        view_mode = render_inventory_view_mode(category, inventory_df)
        editable = can_edit and selected_date == current_date
        if view_mode == "整体黑白统计":
            st.caption(t("整体黑白统计为只读汇总；修改库存请切换到品牌明细"))
            render_black_white_color_summary(
                category, inventory_df, visible_sizes, filter_title
            )
        else:
            if not can_edit:
                st.info(t("当前账号只有库存查看权限，不能修改库存"))
            elif selected_date != current_date:
                st.info(t("历史库存为只读记录，请切换到今天修改当前库存"))
                st.button(
                    t("切换到今天修改"),
                    key="inventory_switch_to_today",
                    on_click=_select_current_inventory_date,
                    args=(current_date,),
                )
            render_inventory_table(
                supabase, department, category, inventory_df, inventory_date,
                editable, visible_sizes, filter_title,
            )
            render_inventory_metrics(inventory_df)

    with tabs["点货预测"]:
        order_quantity, arrival_date, buffer_days = (
            render_consumption_planning_inputs(category)
        )
        forecast_usage_df = render_reorder_forecast(
            supabase, department, category, inventory_df, order_quantity,
            arrival_date, buffer_days, inventory_date, visible_sizes,
        )
        if selected_date == current_date:
            render_incoming_inventory_forecast(
                supabase, department, category, raw_df, current_date,
                forecast_usage_df,
            )
    with tabs["消耗模型"]:
        render_consumption_models(
            supabase, department, category, order_quantity,
            current_date, visible_sizes, raw_df,
        )

    if "仓库每日出库" in tabs:
        with tabs["仓库每日出库"]:
            if not can_edit:
                st.info(t("当前账号只有库存查看权限，不能修改库存"))
            else:
                render_daily_outbound_operation(
                    supabase, department, "黑白短袖", raw_df, can_edit,
                )

    if "系统库存扣减" in tabs:
        with tabs["系统库存扣减"]:
            if not can_edit:
                st.info(t("当前账号只有库存查看权限，不能修改库存"))
            elif department == "DTF":
                render_colored_daily_deduction(supabase, current_date)
            elif department == "UV":
                render_uv_daily_deduction(supabase, current_date)

    with tabs["临时库存调整"]:
        render_temporary_movement_operation(
            supabase, department, category, raw_df, inventory_df, can_edit,
        )

    with tabs["库存流水"]:
        _render_history(
            supabase, department, "all", history_data, visible_sizes,
            movement_types, quantity_search_data=undo_history_data,
        )

    with tabs["SKU 操作历史"]:
        render_sku_operation_history(
            raw_df, history_data, visible_sizes
        )

    with tabs["撤销"]:
        _render_history(
            supabase, department, "undo",
            undo_history_data or history_data, visible_sizes,
            movement_types,
        )

    with tabs["SKU 管理"]:
        sku_tab, initialization_tab, sku_history_tab = st.tabs([
            t("SKU 管理"), t("待初始化库存"), t("SKU 导入历史"),
        ])
        with sku_tab:
            render_sku_management(
                supabase,
                department,
                has_permission("can_manage_sku"),
                sku_filters,
            )
        with initialization_tab:
            render_inventory_initialization(
                supabase, department, category, can_edit,
            )
        with sku_history_tab:
            _render_history(
                supabase, department, "sku", history_data, visible_sizes,
                movement_types,
            )

    if can_view_cost:
        with tabs["库存成本"]:
            render_inventory_cost_summary(
                supabase, department, category, current_cost_df, raw_df
            )


def inventory_tab_keys(department, can_view_cost=False, category=""):
    keys = ["库存明细", "点货预测", "消耗模型"]
    department = str(department or "").strip().upper()
    category = str(category or "").strip()
    if department == "DTF" and category in {"", "黑白短袖"}:
        keys.append("仓库每日出库")
    if (
        department == "UV"
        or (department == "DTF" and category in {"", "彩色短袖"})
    ):
        keys.append("系统库存扣减")
    keys.extend([
        "临时库存调整", "库存流水", "SKU 操作历史", "撤销", "SKU 管理",
    ])
    if can_view_cost:
        keys.append("库存成本")
    return keys


def _render_history(
    supabase, department, mode, history_data, visible_sizes, movement_types,
    quantity_search_data=None,
):
    render_inventory_history(
        supabase, department, mode, history_data=history_data,
        visible_sizes=visible_sizes,
        movement_types=movement_types,
        quantity_search_data=quantity_search_data,
    )


def _select_current_inventory_date(current_date):
    st.session_state["inventory_global_snapshot_date"] = current_date
