"""SKU-first consumable cost maintenance."""

import pandas as pd
import streamlit as st

from db.batches import (
    InboundBatchKind,
    InboundBatchReference,
    InboundCostCorrection,
    filter_active_batch_records,
    replace_inbound_batch,
)
from ui.consumables.units import entry_unit, to_entry_quantity
from utils.auth import get_current_operator_name


def build_consumable_cost_sources(batches_df, movements_df):
    batches = pd.DataFrame(batches_df).copy()
    movements = pd.DataFrame(movements_df).copy()
    if batches.empty or movements.empty:
        return {}, {}
    active_batches = filter_active_batch_records(
        batches, type_column="movement_type"
    )
    active_ids = set(active_batches["id"].astype(str))
    movements = movements[
        movements["batch_id"].astype(str).isin(active_ids)
    ].copy()
    movements["quantity_change"] = pd.to_numeric(
        movements["quantity_change"], errors="coerce"
    ).fillna(0)
    inbound = movements[movements["quantity_change"] > 0].copy()
    if inbound.empty:
        return {}, {}
    inbound["created_at"] = pd.to_datetime(
        inbound["created_at"], errors="coerce", utc=True
    )
    inbound = inbound.sort_values("created_at", ascending=False)
    targets = (
        inbound.drop_duplicates("item_id")
        .set_index("item_id")["id"].astype(str).to_dict()
    )
    inbound["unit_cost"] = pd.to_numeric(
        inbound["unit_cost"], errors="coerce"
    )
    priced = inbound[inbound["unit_cost"].gt(0)]
    latest_costs = (
        priced.drop_duplicates("item_id")
        .set_index("item_id")["unit_cost"].to_dict()
    )
    return latest_costs, targets


def build_consumable_cost_sync_targets(batches_df, movements_df):
    """Map each SKU's current cost record to every active missing-cost inbound."""
    batches = pd.DataFrame(batches_df).copy()
    movements = pd.DataFrame(movements_df).copy()
    if batches.empty or movements.empty:
        return {}, {}
    active_batches = filter_active_batch_records(
        batches, type_column="movement_type"
    )
    active_ids = set(active_batches["id"].astype(str))
    movements = movements[
        movements["batch_id"].astype(str).isin(active_ids)
    ].copy()
    movements["quantity_change"] = pd.to_numeric(
        movements["quantity_change"], errors="coerce"
    ).fillna(0)
    inbound = movements[movements["quantity_change"] > 0].copy()
    if inbound.empty:
        return {}, {}
    inbound["created_at"] = pd.to_datetime(
        inbound["created_at"], errors="coerce", utc=True
    )
    inbound["unit_cost"] = pd.to_numeric(
        inbound["unit_cost"], errors="coerce"
    )
    inbound = inbound.sort_values("created_at", ascending=False)
    latest = inbound.drop_duplicates("item_id").copy()
    latest_ids = latest.set_index("item_id")["id"].astype(str).to_dict()
    missing = inbound[inbound["unit_cost"].isna() | inbound["unit_cost"].le(0)]
    missing_ids = {
        str(item_id): group["id"].astype(str).tolist()
        for item_id, group in missing.groupby(missing["item_id"].astype(str))
    }
    targets = {}
    counts = {}
    for item_id, latest_id in latest_ids.items():
        item_key = str(item_id)
        target_ids = list(dict.fromkeys(
            [latest_id, *missing_ids.get(item_key, [])]
        ))
        targets[latest_id] = target_ids
        counts[item_key] = len(missing_ids.get(item_key, []))
    return targets, counts


def build_consumable_cost_table(
    items_df, latest_costs, cost_record_ids=None, pending_counts=None,
):
    data = pd.DataFrame(items_df).copy()
    columns = [
        "成本记录ID", "分类", "耗材名称", "规格/型号", "品牌",
        "当前库存", "单位", "单位成本", "库存金额", "待同步批次", "成本状态",
    ]
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["current_quantity"] = pd.to_numeric(
        data["current_quantity"], errors="coerce"
    ).fillna(0)
    data = data[data["current_quantity"] > 0].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["单位成本"] = pd.to_numeric(
        data["id"].astype(str).map(latest_costs), errors="coerce"
    ).astype(float)
    data["成本记录ID"] = data["id"].astype(str).map(cost_record_ids or {})
    data["待同步批次"] = (
        data["id"].astype(str).map(pending_counts or {}).fillna(0).astype(int)
    )
    data["当前库存"] = data.apply(
        lambda row: to_entry_quantity(row["current_quantity"], row), axis=1
    )
    data["单位"] = data.apply(entry_unit, axis=1)
    base_quantity = data["current_quantity"]
    data["库存金额"] = base_quantity * data["单位成本"].fillna(0)
    data["成本状态"] = data["单位成本"].gt(0).map({
        True: "已填写", False: "缺成本",
    })
    return data.rename(columns={
        "category": "分类", "name": "耗材名称",
        "specification": "规格/型号", "brand": "品牌",
    })[columns].reset_index(drop=True)


def find_consumable_cost_changes(original, edited):
    changes = []
    unresolved = []
    for old_row, new_row in zip(
        pd.DataFrame(original).to_dict("records"),
        pd.DataFrame(edited).to_dict("records"),
    ):
        old_cost = pd.to_numeric(old_row.get("单位成本"), errors="coerce")
        new_cost = pd.to_numeric(new_row.get("单位成本"), errors="coerce")
        if pd.isna(new_cost) or new_cost <= 0:
            continue
        pending_count = int(old_row.get("待同步批次") or 0)
        if (
            not pd.isna(old_cost)
            and abs(float(new_cost) - float(old_cost)) <= 0.00005
            and pending_count == 0
        ):
            continue
        record_id = str(old_row.get("成本记录ID") or "").strip()
        if not record_id:
            unresolved.append(
                "｜".join(str(new_row.get(column) or "") for column in [
                    "分类", "耗材名称", "规格/型号", "品牌",
                ])
            )
            continue
        changes.append((record_id, round(float(new_cost), 4)))
    return changes, unresolved


def render_consumable_cost_workspace(
    supabase, items_df, batches_df, movements_df, can_manage_cost,
):
    latest_costs, cost_record_ids = build_consumable_cost_sources(
        batches_df, movements_df
    )
    sync_targets, pending_counts = build_consumable_cost_sync_targets(
        batches_df, movements_df
    )
    st.subheader("SKU 价格完成情况")
    cost_table = build_consumable_cost_table(
        items_df, latest_costs, cost_record_ids, pending_counts
    )
    priced = int(cost_table["单位成本"].gt(0).sum()) if not cost_table.empty else 0
    total = len(cost_table)
    metrics = st.columns(3)
    metrics[0].metric("有库存 SKU", f"{total:,}")
    metrics[1].metric("已输入价格", f"{priced:,}")
    metrics[2].metric("未输入价格", f"{total - priced:,}")
    if total - priced:
        st.warning(f"还有 {total - priced:,} 个耗材 SKU 未输入价格。")
    elif total:
        st.success("当前范围内所有耗材 SKU 都已输入价格。")

    st.markdown("#### SKU 价格与当前库存金额")
    if not can_manage_cost:
        st.info("当前账号可以查看成本，但不能修改 SKU 价格。")
    version = st.session_state.get("consumable_cost_editor_version", 0)
    edited = pd.DataFrame(st.data_editor(
        cost_table,
        hide_index=True,
        width="stretch",
        disabled=[
            "成本记录ID", "分类", "耗材名称", "规格/型号", "品牌",
            "当前库存", "单位", "库存金额", "待同步批次", "成本状态",
        ],
        column_config={
            "成本记录ID": None,
            "当前库存": st.column_config.NumberColumn(format="%.2f"),
            "单位成本": st.column_config.NumberColumn(
                min_value=0.0001, step=0.0001, format="$%.4f"
            ),
            "库存金额": st.column_config.NumberColumn(format="$%.2f"),
        },
        key=f"consumable_sku_cost_editor_{version}",
    ))
    st.caption(
        "这里只维护每个耗材 SKU 的当前价格；保存后库存金额自动重算。"
        "待同步批次表示同一 SKU 仍有缺价入库记录；保存时会一并补价，"
        "但不会覆盖已有历史价格。历史入库批次与明细留在财务页面展示。"
    )
    if not can_manage_cost:
        return
    if not st.button("保存 SKU 价格", width="stretch", type="primary"):
        return
    changes, unresolved = find_consumable_cost_changes(cost_table, edited)
    if unresolved:
        st.error(
            "以下 SKU 没有可关联的有效入库记录，暂时不能保存价格："
            + "；".join(unresolved)
        )
        return
    if not changes:
        st.warning("请先修改需要保存的 SKU 单位成本。")
        return
    updated_movements = 0
    for movement_id, unit_cost in changes:
        for target_id in sync_targets.get(movement_id, [movement_id]):
            replace_inbound_batch(
                supabase,
                InboundBatchReference(
                    InboundBatchKind.CONSUMABLE_MOVEMENT, target_id
                ),
                InboundCostCorrection(unit_cost),
                get_current_operator_name(),
            )
            updated_movements += 1
    for key in list(st.session_state):
        if str(key).startswith("inventory_cost_history_data_"):
            st.session_state.pop(key, None)
    st.session_state["consumable_saved_message"] = (
        f"已更新 {len(changes)} 个耗材 SKU，并同步 "
        f"{updated_movements} 条有效入库成本记录。"
    )
    st.session_state["consumable_cost_editor_version"] = version + 1
    st.rerun()
