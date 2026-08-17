import pandas as pd
import streamlit as st

from db.batches import (
    ContainerInboundCorrection,
    InboundBatchKind,
    InboundBatchReference,
    replace_inbound_batch,
)
from db.inventory.container.editor import update_container_items
from utils.auth import get_current_operator_name, has_permission
from utils.sku_sorting import sort_sku_rows
from ui.table_layout import fit_table_height
from ui.inventory.container.posting import (
    render_container_inventory_change_review,
)


DISPLAY_COLUMNS = {
    "id": "记录ID", "expected_arrival_date": "预计到货日期",
    "category": "品类", "brand": "品牌", "material": "材质",
    "color": "颜色", "size": "型号", "quantity": "数量",
    "unit_cost": "成本", "note": "备注",
}


def render_container_item_editor(supabase, target, container_key, can_edit):
    if not can_edit:
        return
    statuses = set(target["status"].fillna("").astype(str))
    if statuses == {"已入库"}:
        st.caption("已入库货柜请在“库存 → 库存流水”选择原入库批次统一更正。")
        return
    source = build_container_item_editor_source(target)
    st.subheader("修改货柜明细")
    edited = st.data_editor(
        source, hide_index=True, width="stretch",
        disabled=["记录ID"], key=f"container_item_editor_{container_key}",
        column_config={
            "记录ID": None,
            "预计到货日期": st.column_config.DateColumn(),
            "数量": st.column_config.NumberColumn(min_value=0, step=1),
            "成本": st.column_config.NumberColumn(min_value=0.0, step=0.0001, format="%.4f"),
        },
        height=fit_table_height(source),
    )
    if st.button("保存货柜明细修改", type="primary", key=f"save_container_items_{container_key}"):
        updates = {}
        reverse = {value: key for key, value in DISPLAY_COLUMNS.items()}
        for row in edited.to_dict("records"):
            item_id = str(row.pop("记录ID"))
            values = {reverse[key]: value for key, value in row.items()}
            values["expected_arrival_date"] = values["expected_arrival_date"].isoformat()
            updates[item_id] = values
        try:
            result = update_container_items(
                supabase, container_key, updates, get_current_operator_name()
            )
            st.success(f"已保存 {result['rows']} 行修改")
            st.rerun()
        except Exception as error:
            st.error(f"货柜明细保存失败：{error}")


def render_posted_container_correction(supabase, target, container_key):
    st.subheader("更正入库批次")
    st.caption(
        "在同一批次修改数量和成本。数量变化生成独立库存更正流水；"
        "成本变化同步货柜、原入库流水、成本批次和已发生的成本分摊。"
    )
    source = build_container_item_editor_source(target)
    can_edit_cost = has_permission("can_view_cost")
    editor_source = source if can_edit_cost else source.drop(
        columns=["成本"], errors="ignore"
    )
    editable_columns = {"数量", "成本"} if can_edit_cost else {"数量"}
    edited = st.data_editor(
        editor_source, hide_index=True, width="stretch",
        disabled=[
            column for column in editor_source.columns
            if column not in editable_columns
        ],
        key=f"posted_container_item_editor_{container_key}",
        column_config={
            "记录ID": None,
            "预计到货日期": st.column_config.DateColumn(),
            "数量": st.column_config.NumberColumn(min_value=0, step=1),
            "成本": st.column_config.NumberColumn(format="%.4f"),
        },
        height=fit_table_height(editor_source),
    )
    original = source.set_index("记录ID")["数量"].astype(int)
    revised = edited.set_index("记录ID")["数量"].astype(int)
    quantity_changed = revised[revised != original]
    original_cost = pd.Series(dtype=float)
    revised_cost = pd.Series(dtype=float)
    cost_changed = pd.Series(dtype=float)
    if can_edit_cost:
        original_cost = pd.to_numeric(
            source.set_index("记录ID")["成本"], errors="coerce"
        ).fillna(0).round(4)
        revised_cost = pd.to_numeric(
            edited.set_index("记录ID")["成本"], errors="coerce"
        )
        if revised_cost.isna().any():
            st.error("成本必须是有效数字。")
            return
        revised_cost = revised_cost.round(4)
        cost_changed = revised_cost[revised_cost != original_cost]
        if (cost_changed <= 0).any():
            st.error("修改后的成本必须大于 0。")
            return
    if quantity_changed.empty and cost_changed.empty:
        st.info("修改数量或成本后，这里会显示更正汇总。")
        return
    if not quantity_changed.empty:
        difference = int(
            quantity_changed.sum() - original.loc[quantity_changed.index].sum()
        )
        st.metric("货柜数量变化", f"{difference:+,} 件")
        correction_rows = target[
            target["id"].astype(str).isin(
                quantity_changed.index.astype(str)
            )
        ].copy()
        revised_by_id = {
            str(key): int(value) for key, value in quantity_changed.items()
        }
        correction_rows["_revised_quantity"] = correction_rows[
            "id"
        ].astype(str).map(revised_by_id)
        quantity_difference = (
            correction_rows["_revised_quantity"].astype(int)
            - pd.to_numeric(
                correction_rows["quantity"], errors="coerce"
            ).fillna(0).astype(int)
        )
        correction_rows["操作"] = quantity_difference.map(
            lambda value: "增加" if value > 0 else "扣减"
        )
        correction_rows["quantity"] = quantity_difference.abs()
        render_container_inventory_change_review(
            supabase, correction_rows, None, "更正后的库存核对"
        )
    if not cost_changed.empty:
        before = float((original * original_cost).sum())
        after = float((revised * revised_cost).sum())
        st.metric("本批成本变化", f"${after - before:+,.2f}")
    confirmed = st.checkbox(
        "我已核对数量与成本，并确认同步库存、成本及保留更正历史",
        key=f"confirm_posted_container_correction_{container_key}",
    )
    if not st.button(
        "保存入库后更正", type="primary", width="stretch",
        disabled=not confirmed,
        key=f"save_posted_container_correction_{container_key}",
    ):
        return
    try:
        operator = get_current_operator_name()
        result = replace_inbound_batch(
            supabase,
            InboundBatchReference(InboundBatchKind.CONTAINER, container_key),
            ContainerInboundCorrection(
                quantity_updates={
                    str(key): int(value)
                    for key, value in quantity_changed.items()
                },
                item_costs={
                    str(key): float(value)
                    for key, value in cost_changed.items()
                },
            ),
            operator,
        )
        quantity_result = result["quantity"]
        cost_result = result["cost"]
    except Exception as error:
        st.error(f"已入库货柜更正失败：{error}")
        return
    st.session_state["inventory_saved_message"] = (
        f"已更正数量 {quantity_result['rows']} 行、成本 "
        f"{cost_result['rows']} 行；库存同步 "
        f"{quantity_result['inventory_change']:+,} 件；"
        f"已消耗历史差额 "
        f"{quantity_result['unresolved_shortage']:,} 件"
    )
    st.rerun()


def build_container_item_editor_source(target):
    source = target[list(DISPLAY_COLUMNS)].rename(columns=DISPLAY_COLUMNS).copy()
    source["预计到货日期"] = pd.to_datetime(
        source["预计到货日期"], errors="coerce"
    ).dt.date
    return sort_sku_rows(
        source,
        material="材质", color="颜色", size="型号",
        leading=["材质", "品牌"],
    )
