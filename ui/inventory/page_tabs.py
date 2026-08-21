from hashlib import sha1

import streamlit as st

from db.inventory import build_inventory_table
from ui.inventory.history.workflows.page import (
    render_inventory_history,
)
from ui.inventory.history.workflows.revisions import (
    render_daily_outbound_revision_history,
)
from ui.inventory.i18n import t
from ui.inventory.operations.pages import (
    render_daily_outbound_operation,
    render_temporary_movement_operation,
)
from ui.inventory.planning.comparison import render_consumption_models
from ui.inventory.planning.uv_view import render_uv_daily_deduction
from ui.inventory.planning.colored_consumption import (
    render_colored_daily_deduction,
)
from ui.inventory.planning.consumption import (
    DEFAULT_ORDER_QUANTITY,
    render_consumption_planning_inputs,
    render_reorder_forecast,
)
from ui.inventory.stock.cost_summary import render_inventory_cost_summary
from ui.inventory.stock.batch_costs import (
    build_missing_cost_batch_overview,
    filter_cost_history_scope,
    render_inbound_cost_editor,
    render_reference_cost_fill,
)
from ui.inventory.stock.incoming import render_incoming_inventory_forecast
from ui.inventory.stock.summary import (
    render_black_white_color_summary,
    render_colored_brand_merged_summary,
)
from ui.inventory.stock.table import (
    render_inventory_metrics,
    render_inventory_table,
    render_sku_update_times,
    render_inventory_view_mode,
)
from ui.table_layout import fit_table_height


def render_inventory_tabs(
    supabase, department, category, inventory_df, raw_df,
    inventory_date, selected_date, current_date, visible_sizes, can_edit,
    can_view_cost, history_data, movement_types, filter_title,
    undo_history_data=None, operation_inventory_df=None,
    operation_raw_df=None,
    history_filter_active=False,
):
    tab_keys = inventory_tab_keys(
        department, can_view_cost=can_view_cost, category=category
    )
    tab_names = [t(name) for name in tab_keys]
    tabs = dict(zip(tab_keys, st.tabs(
        tab_names, key=inventory_tab_state_key(department, category),
        on_change="rerun"
    )))

    if tabs["库存明细"].open:
        with tabs["库存明细"]:
            view_mode = render_inventory_view_mode(category, inventory_df)
            editable = can_edit and selected_date == current_date
            if view_mode == "整体黑白统计":
                st.caption(t("整体黑白统计为只读汇总；修改库存请切换到品牌明细"))
                render_black_white_color_summary(
                    category, inventory_df, visible_sizes, filter_title
                )
            elif view_mode == "跨品牌合并":
                render_colored_brand_merged_summary(
                    inventory_df, visible_sizes, filter_title
                )
                render_inventory_metrics(inventory_df)
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
                    is_historical=selected_date < current_date,
                )
                render_inventory_metrics(inventory_df)
            if selected_date == current_date:
                render_sku_update_times(raw_df, department, visible_sizes)

    if tabs["点货预测"].open:
        with tabs["点货预测"]:
            order_quantity, arrival_date, buffer_days, target_days = (
                render_consumption_planning_inputs(category)
            )
            forecast_usage_df = render_reorder_forecast(
                supabase, department, category, inventory_df, order_quantity,
                arrival_date, buffer_days, inventory_date, visible_sizes,
                target_days=target_days,
            )
            if selected_date == current_date:
                render_incoming_inventory_forecast(
                    supabase, department, category, raw_df, current_date,
                    forecast_usage_df, target_days=target_days,
                )
    if tabs["消耗模型"].open:
        with tabs["消耗模型"]:
            order_quantity = st.session_state.get(
                "haloo_consumption_order_quantity", DEFAULT_ORDER_QUANTITY
            )
            render_consumption_models(
                supabase, department, category, order_quantity,
                current_date, visible_sizes, raw_df,
            )

    if "仓库每日出库" in tabs and tabs["仓库每日出库"].open:
        with tabs["仓库每日出库"]:
            if not can_edit:
                st.info(t("当前账号只有库存查看权限，不能修改库存"))
            else:
                render_daily_outbound_operation(
                    supabase, department, "黑白短袖", raw_df, can_edit,
                )

    if "系统库存扣减" in tabs and tabs["系统库存扣减"].open:
        with tabs["系统库存扣减"]:
            if not can_edit:
                st.info(t("当前账号只有库存查看权限，不能修改库存"))
            elif department == "DTF":
                render_colored_daily_deduction(supabase, current_date)
            elif department == "UV":
                render_uv_daily_deduction(supabase, current_date)

    if tabs["临时库存调整"].open:
        with tabs["临时库存调整"]:
            render_temporary_movement_operation(
                supabase, department, category,
                operation_raw_df if operation_raw_df is not None else raw_df,
                operation_inventory_df if operation_inventory_df is not None
                else inventory_df,
                can_edit,
            )

    if tabs["库存流水"].open:
        with tabs["库存流水"]:
            st.caption(f"{t('当前流水筛选')}：{filter_title}")
            _render_history(
                supabase, department, "all", history_data, visible_sizes,
                movement_types, quantity_search_data=undo_history_data,
                show_all_filtered=history_filter_active,
            )

    if tabs["批次修改与撤销"].open:
        with tabs["批次修改与撤销"]:
            st.caption(
                "选择完整业务批次后，可以修改替换、数量校准或整批撤销；"
                "原批次、修正版和撤销记录都会保留。"
            )
            if department == "DTF" and category in {"", "黑白短袖"}:
                with st.expander("每日出库版本历史", expanded=False):
                    render_daily_outbound_revision_history(
                        supabase, department, "黑白短袖"
                    )
            _render_history(
                supabase, department, "undo",
                undo_history_data or history_data, visible_sizes,
                movement_types,
            )

    if can_view_cost and tabs["库存成本"].open:
        with tabs["库存成本"]:
            with st.spinner("正在计算当前库存成本…"):
                current_cost_df = build_inventory_table(
                    raw_df, category, include_cost=True,
                    department=department,
                )
            render_inventory_cost_summary(
                supabase, department, category, current_cost_df, raw_df
            )
            st.divider()
            st.subheader("入库批次成本（第二步）")
            st.caption(
                "先确认上方每个 SKU 是否已输入价格，再核对价格是否覆盖"
                "到具体入库批次。成本修改统一在库存处理；财务页面只展示结果。"
            )
            from utils.auth import has_permission

            if not has_permission("can_manage_cost"):
                st.info("当前账号可以查看成本，但不能修改入库批次成本。")
            else:
                _render_batch_cost_workspace(
                    supabase, department, category
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
        "临时库存调整", "库存流水", "批次修改与撤销",
    ])
    if can_view_cost:
        keys.append("库存成本")
    return keys


def inventory_tab_state_key(department, category=""):
    scope = sha1(f"{department}|{category}".encode()).hexdigest()[:10]
    return f"inventory_workspace_{scope}"


def _render_batch_cost_workspace(supabase, department, category):
    """Keep the large inbound ledger off the normal inventory refresh path."""
    scope = f"{department}|{category}"
    signature = sha1(scope.encode()).hexdigest()[:12]
    cache_key = f"inventory_cost_history_data_{signature}"
    loaded = cache_key in st.session_state

    if loaded:
        if st.button(
            "刷新入库批次成本", width="stretch",
            key=f"refresh_inventory_cost_history_{signature}",
        ):
            st.session_state.pop(cache_key, None)
            loaded = False
    elif st.button(
        "加载入库批次成本", width="stretch", type="primary",
        key=f"load_inventory_cost_history_{signature}",
    ):
        loaded = True

    if not loaded:
        st.info(
            "当前库存成本已经显示。只有需要补价或修改历史入库批次时，"
            "才加载完整批次成本，避免每次刷新库存都等待。"
        )
        return

    if cache_key not in st.session_state:
        from db.finance import load_inbound_cost_history

        with st.status("正在加载入库批次成本…", expanded=True) as status:
            status.write("正在读取完整入库成本流水")
            cost_history = filter_cost_history_scope(
                load_inbound_cost_history(supabase), department, category
            )
            st.session_state[cache_key] = cost_history
            status.update(
                label=f"入库批次成本已加载，共 {len(cost_history):,} 条",
                state="complete", expanded=False,
            )
    cost_history = st.session_state[cache_key]
    missing_batches = build_missing_cost_batch_overview(cost_history)
    st.subheader("缺成本批次概览")
    if missing_batches.empty:
        st.success("当前范围内所有入库批次都已填写成本。")
    else:
        metric_columns = st.columns(3)
        metric_columns[0].metric("缺成本批次", f"{len(missing_batches):,}")
        metric_columns[1].metric(
            "缺成本 SKU",
            f"{int(missing_batches['缺成本 SKU 数'].sum()):,}",
        )
        metric_columns[2].metric(
            "批次原始数量",
            f"{int(missing_batches['批次数量'].sum()):,}",
        )
        st.dataframe(
            missing_batches,
            hide_index=True,
            width="stretch",
            height=fit_table_height(missing_batches),
            column_config={
                "缺成本 SKU 数": st.column_config.NumberColumn(format="%d"),
                "批次数量": st.column_config.NumberColumn(format="%d"),
            },
        )
        st.caption(
            "这里显示批次原始数量；财务汇总中的缺成本库存只统计当前尚余数量。"
        )
    st.divider()
    render_reference_cost_fill(
        supabase, cost_history, history_cache_key=cache_key
    )
    st.subheader("按入库批次维护成本")
    render_inbound_cost_editor(
        supabase, cost_history, history_cache_key=cache_key
    )


def _render_history(
    supabase, department, mode, history_data, visible_sizes, movement_types,
    quantity_search_data=None, show_all_filtered=False,
):
    render_inventory_history(
        supabase, department, mode, history_data=history_data,
        visible_sizes=visible_sizes,
        movement_types=movement_types,
        quantity_search_data=quantity_search_data,
        show_all_filtered=show_all_filtered,
    )


def _select_current_inventory_date(current_date):
    st.session_state["inventory_global_snapshot_date"] = current_date
