from hashlib import sha1

import pandas as pd
import streamlit as st

from db.batches import (
    InboundBatchKind,
    InboundBatchReference,
    InboundCostCorrection,
    replace_inbound_batch,
)
from utils.auth import get_current_operator_name
from utils.sku_sorting import sort_sku_rows


SOURCE_LABELS = {
    "opening": "初始化库存",
    "bulk": "正常入库",
    "transfer": "临时调货",
    "consumable_inbound": "耗材入库",
    "consumable_adjustment": "耗材库存修正",
}


def render_inbound_cost_editor(supabase, finance_df):
    saved = st.session_state.pop("finance_cost_saved", None)
    if saved:
        st.success(saved)

    prepared = _prepare_inbound(finance_df)
    summary = build_cost_batch_summary(prepared)
    if summary.empty:
        st.info("当前没有需要补成本或可修改的入库批次")
        return

    st.caption(
        "先选择批次，再查看和修改该批次的 SKU 成本；缺成本批次优先显示。"
    )
    options = summary["批次键"].tolist()
    labels = {
        row["批次键"]: (
            f"{row['日期']}｜{row['来源']}｜{row['部门']} {row['品类']}｜"
            f"{int(row['SKU数']):,} SKU｜{int(row['数量']):,} 件｜{row['状态']}"
        )
        for row in summary.to_dict("records")
    }
    version = st.session_state.get("finance_cost_editor_version", 0)
    signature = sha1("|".join(options).encode()).hexdigest()[:10]
    selected = st.selectbox(
        "选择成本批次",
        options,
        format_func=lambda value: labels.get(value, value),
        key=f"finance_cost_batch_{version}_{signature}",
    )
    selected_summary = summary[summary["批次键"] == selected].iloc[0]
    metric_columns = st.columns(3)
    metric_columns[0].metric("批次 SKU", f"{int(selected_summary['SKU数']):,}")
    metric_columns[1].metric("批次数量", f"{int(selected_summary['数量']):,}")
    metric_columns[2].metric("缺成本 SKU", f"{int(selected_summary['缺成本SKU']):,}")

    inbound = _build_editor_data(
        prepared[prepared["_batch_key"] == selected]
    )
    st.markdown("#### 批次明细与价格")
    st.caption(
        "填写单位成本后，会同步修正该批次的现有库存金额和历史出库成本。"
    )
    edited = pd.DataFrame(st.data_editor(
        inbound,
        width="stretch",
        hide_index=True,
        disabled=[
            "批次ID", "日期", "来源", "部门", "品类", "品牌",
            "材质", "颜色", "尺码/型号", "数量", "成本状态",
        ],
        column_config={
            "批次ID": None,
            "日期": st.column_config.DateColumn("日期"),
            "数量": st.column_config.NumberColumn("数量", format="%d"),
            "单位成本": st.column_config.NumberColumn(
                "单位成本",
                min_value=0.0001,
                step=0.0001,
                format="$%.4f",
            ),
        },
        key=f"finance_inbound_cost_editor_{version}_{signature}",
    ))
    if not st.button(
        "保存这个批次的成本",
        width="stretch",
        key=f"save_finance_cost_{version}_{signature}",
    ):
        return

    changes = find_cost_changes(inbound, edited)
    if not changes:
        st.warning("请先修改需要保存的单位成本")
        return
    source_by_record = prepared.set_index("record_id")[
        "source_type"
    ].to_dict()
    for cost_lot_id, unit_cost in changes:
        source_type = str(source_by_record.get(cost_lot_id) or "")
        kind = (
            InboundBatchKind.CONSUMABLE_MOVEMENT
            if source_type.startswith("consumable_")
            else InboundBatchKind.INVENTORY_COST_LOT
        )
        replace_inbound_batch(
            supabase,
            InboundBatchReference(kind, cost_lot_id),
            InboundCostCorrection(unit_cost),
            get_current_operator_name(),
        )
    st.session_state["finance_cost_saved"] = (
        f"已更新这个批次中 {len(changes)} 个 SKU 的成本"
    )
    st.session_state["finance_cost_editor_version"] = version + 1
    st.rerun()


def build_cost_batch_summary(finance_df):
    prepared = (
        finance_df if "_batch_key" in finance_df else _prepare_inbound(finance_df)
    )
    columns = [
        "批次键", "日期", "来源", "部门", "品类",
        "SKU数", "数量", "缺成本SKU", "状态",
    ]
    if prepared.empty:
        return pd.DataFrame(columns=columns)
    data = prepared.copy()
    data["_missing"] = data["unit_cost"].isna().astype(int)
    result = (
        data.groupby("_batch_key", as_index=False)
        .agg(
            date=("date", "max"),
            source_type=("source_type", "first"),
            department=("department", "first"),
            category=("category", "first"),
            sku_count=("record_id", "count"),
            quantity=("quantity", "sum"),
            missing_count=("_missing", "sum"),
        )
        .rename(columns={
            "_batch_key": "批次键", "date": "日期",
            "source_type": "来源", "department": "部门",
            "category": "品类", "sku_count": "SKU数",
            "quantity": "数量", "missing_count": "缺成本SKU",
        })
    )
    result["来源"] = result["来源"].map(SOURCE_LABELS).fillna(result["来源"])
    result["状态"] = result["缺成本SKU"].apply(
        lambda count: f"缺成本 {int(count)}" if count else "已填写"
    )
    result["_complete"] = (result["缺成本SKU"] == 0).astype(int)
    return result.sort_values(
        ["_complete", "日期"], ascending=[True, False]
    ).drop(columns=["_complete"])[columns].reset_index(drop=True)


def _prepare_inbound(finance_df):
    if finance_df.empty:
        return finance_df.copy()
    inbound = finance_df[
        (finance_df["direction"] == "入库")
        & finance_df["record_id"].notna()
    ].copy()
    if inbound.empty:
        return inbound
    batch_ids = inbound.get(
        "batch_id", pd.Series("", index=inbound.index)
    ).fillna("").astype(str)
    legacy_keys = (
        "初始化::"
        + inbound["date"].astype(str)
        + "::" + inbound["source_type"].fillna("").astype(str)
        + "::" + inbound["department"].fillna("").astype(str)
        + "::" + inbound["category"].fillna("").astype(str)
    )
    inbound["_batch_key"] = batch_ids.where(
        batch_ids.str.strip() != "", legacy_keys
    )
    return inbound


def find_cost_changes(original, edited):
    original_costs = original.set_index("批次ID")["单位成本"]
    changes = []
    for row in edited.to_dict("records"):
        cost_lot_id = row["批次ID"]
        new_cost = pd.to_numeric(row.get("单位成本"), errors="coerce")
        old_cost = pd.to_numeric(
            original_costs.get(cost_lot_id), errors="coerce"
        )
        if pd.isna(new_cost) or new_cost <= 0:
            continue
        if pd.isna(old_cost) or abs(float(new_cost) - float(old_cost)) > 0.00005:
            changes.append((cost_lot_id, round(float(new_cost), 4)))
    return changes


def _build_editor_data(finance_df):
    if finance_df.empty:
        return pd.DataFrame()
    inbound = _prepare_inbound(finance_df)
    if inbound.empty:
        return pd.DataFrame()
    inbound["source_type"] = inbound["source_type"].map(
        SOURCE_LABELS
    ).fillna(inbound["source_type"])
    inbound["成本状态"] = inbound["unit_cost"].apply(
        lambda value: "缺成本" if pd.isna(value) else "已填写"
    )
    result = inbound.rename(columns={
        "record_id": "批次ID",
        "date": "日期",
        "source_type": "来源",
        "department": "部门",
        "category": "品类",
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "size": "尺码/型号",
        "quantity": "数量",
        "unit_cost": "单位成本",
    })[[
        "批次ID", "日期", "来源", "部门", "品类", "品牌",
        "材质", "颜色", "尺码/型号", "数量", "成本状态", "单位成本",
    ]]
    result["_missing_order"] = (result["成本状态"] != "缺成本").astype(int)
    result = sort_sku_rows(
        result,
        leading=["_missing_order", "日期"],
        leading_ascending=[True, False],
    )
    return result.drop(columns=["_missing_order"]).reset_index(drop=True)
