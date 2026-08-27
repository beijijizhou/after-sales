"""Inventory history page orchestration."""

import pandas as pd
import streamlit as st

from db.inventory import load_inventory_movements
from db.inventory.sku import load_sku_imports
from ui.inventory.history.core.batch_selector import render_batch_selector
from ui.inventory.history.core.batches import (
    add_movement_batch_key,
    build_movement_batches,
)
from ui.inventory.history.core.filters import (
    filter_batches_by_movement_type,
    filter_batches_by_outbound_kind,
    filter_history_batches,
    filter_reversal_scope,
)
from ui.inventory.history.core.quantity_search import (
    render_outbound_quantity_search,
)
from ui.inventory.history.core.tables import render_movement_table
from ui.inventory.history.workflows.reversal import render_selected_movement
from ui.inventory.history.workflows.sku_history import (
    render_selected_sku_import,
)
from ui.inventory.i18n import t
from ui.inventory.shared import filter_inventory_rows


@st.cache_data(ttl=30, show_spinner=False)
def load_inventory_history_data(_supabase, department, limit=500):
    movements = load_inventory_movements(
        _supabase, department, "", limit=limit
    )
    imports = load_sku_imports(_supabase, department, "", limit=limit)
    return movements, imports, build_movement_batches(movements, imports)


def clear_inventory_history_cache():
    load_inventory_history_data.clear()


def filter_inventory_history_data(
    history_data, category, brands, materials, colors, sizes,
):
    movements, imports, _ = history_data
    movements = filter_inventory_rows(
        movements, category, brands, materials, colors, sizes
    )
    imports = filter_inventory_rows(
        imports, category, brands, materials, colors, sizes
    )
    return movements, imports, build_movement_batches(movements, imports)


def render_inventory_history(
    supabase, department, mode, history_data=None, visible_sizes=None,
    movement_types=None, quantity_search_data=None,
    show_all_filtered=False,
):
    history_data = history_data or load_inventory_history_data(
        supabase, department
    )
    movements, imports, batches = filter_history_department(
        history_data, department
    )
    if batches.empty:
        st.info(t("暂无相关记录"))
        return
    selected = filter_history_batches(batches, mode)
    department_key = str(department or "all").strip().lower()
    history_key = f"inventory_{department_key}_{mode}_history_batch"
    if mode == "all":
        selected = _render_ledger_filters(
            selected, movements, quantity_search_data, visible_sizes,
            department, department_key,
        )
        if selected is None:
            return
    if mode == "undo":
        selected, history_key = _render_reversal_filters(
            selected, department_key
        )
    elif mode != "sku":
        selected = filter_batches_by_movement_type(selected, movement_types)
    if mode == "all" and show_all_filtered:
        render_filtered_movement_results(selected, movements, visible_sizes)
        return
    if mode == "sku":
        st.subheader(t("SKU 导入历史"))
    render_history_tab(
        supabase, selected, movements, imports, history_key,
        allow_undo=mode == "undo", visible_sizes=visible_sizes,
        sku_import=mode == "sku",
    )


def _render_ledger_filters(
    selected, movements, quantity_search_data, visible_sizes,
    department, department_key,
):
    kind = st.selectbox(
        t("流水记录类型"),
        ["全部流水", "货柜入库", "每日库存扣减", "临时库存调整", "库存设置"],
        format_func=t, key=f"inventory_{department_key}_ledger_outbound_kind",
    )
    selected = filter_batches_by_outbound_kind(selected, kind)
    complete = quantity_search_data[0] if quantity_search_data else movements
    complete = rows_for_department(complete, department)
    if render_outbound_quantity_search(
        movements, complete, visible_sizes,
        key_prefix=f"inventory_{department_key}_outbound_quantity",
    ):
        return None
    return selected


def _render_reversal_filters(selected, department_key):
    st.caption(
        "这里显示当前部门的完整可撤销批次，不受库存日期、品类、"
        "品牌、材质、颜色或尺码筛选影响。"
    )
    scope = st.segmented_control(
        "撤销记录类型",
        ["全部可撤销记录", "货柜入库", "仓库每日出库", "系统库存扣减",
         "临时库存调整", "库存设置", "其他出入库"],
        default="全部可撤销记录",
        key=f"inventory_{department_key}_reversal_scope",
    ) or "全部可撤销记录"
    selected = filter_reversal_scope(selected, scope)
    st.caption(f"{scope}：当前显示 {len(selected):,} 笔可撤销记录")
    return selected, "inventory_undo_history_batch_" + scope


def render_filtered_movement_results(batch_df, movement_df, visible_sizes=None):
    if batch_df.empty:
        st.info(t("暂无相关记录"))
        return
    st.markdown("#### 筛选结果批次")
    st.caption("当前已开启 SKU 筛选，以下展示全部匹配批次和全部相关流水。")
    st.dataframe(
        batch_df[["记录时间", "表格日期", "类型", "部门", "品类",
                  "数量", "操作人", "消耗来源", "备注"]],
        hide_index=True, width="stretch",
    )
    render_movement_table(
        filter_movements_for_batches(movement_df, batch_df), visible_sizes,
        key="inventory_filtered_movement_details",
    )


def filter_movements_for_batches(movement_df, batch_df):
    if movement_df.empty or batch_df.empty:
        return pd.DataFrame(movement_df).iloc[0:0].copy()
    keyed = add_movement_batch_key(movement_df)
    visible = set(batch_df["batch_key"].astype(str))
    return keyed[
        keyed["batch_key"].astype(str).isin(visible)
    ].reset_index(drop=True)


def filter_history_department(history_data, department):
    movements, imports, _ = history_data
    movements = rows_for_department(movements, department)
    imports = rows_for_department(imports, department)
    return movements, imports, build_movement_batches(movements, imports)


def rows_for_department(rows, department):
    source = pd.DataFrame(rows).copy()
    if source.empty or "department" not in source:
        return source
    expected = str(department or "").strip().casefold()
    values = source["department"].fillna("").astype(str).str.strip().str.casefold()
    return source[values == expected].reset_index(drop=True)


def render_history_tab(
    supabase, batch_df, movement_df, sku_import_df, key, allow_undo=False,
    visible_sizes=None, sku_import=False,
):
    selected = render_batch_selector(batch_df, key=key, sku_import=sku_import)
    if not selected:
        return
    selected_batch = batch_df[batch_df["batch_key"] == selected]
    selected_type = (
        selected_batch.iloc[0]["类型"] if not selected_batch.empty else ""
    )
    if selected_type == "新增 SKU":
        render_selected_sku_import(sku_import_df, selected, visible_sizes)
        return
    render_selected_movement(
        supabase, movement_df, selected, allow_undo=allow_undo,
        visible_sizes=visible_sizes, key_scope=key,
    )
