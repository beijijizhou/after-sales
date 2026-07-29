import pandas as pd
import streamlit as st

from db.finance import update_inbound_lot_cost


SOURCE_LABELS = {
    "bulk": "正常入库",
    "transfer": "临时调货",
}


def render_inbound_cost_editor(supabase, finance_df):
    saved = st.session_state.pop("finance_cost_saved", None)
    if saved:
        st.success(saved)

    with st.expander("修改入库批次成本"):
        inbound = _build_editor_data(finance_df)
        if inbound.empty:
            st.info("本月没有可修改的入库批次")
            return

        st.caption(
            "这里只修改所选入库批次，不会改变其他批次或 SKU 的默认成本。"
        )
        version = st.session_state.get("finance_cost_editor_version", 0)
        edited = pd.DataFrame(st.data_editor(
            inbound,
            width="stretch",
            hide_index=True,
            disabled=[
                "批次ID", "日期", "来源", "部门", "品类", "品牌",
                "材质", "颜色", "尺码/型号", "数量",
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
            key=f"finance_inbound_cost_editor_{version}",
        ))
        if not st.button(
            "保存批次成本",
            width="stretch",
            key=f"save_finance_cost_{version}",
        ):
            return

        changes = find_cost_changes(inbound, edited)
        if not changes:
            st.warning("请先修改需要保存的单位成本")
            return
        for cost_lot_id, unit_cost in changes:
            update_inbound_lot_cost(supabase, cost_lot_id, unit_cost)
        st.session_state["finance_cost_saved"] = (
            f"已更新 {len(changes)} 个入库批次成本"
        )
        st.session_state["finance_cost_editor_version"] = version + 1
        st.rerun()


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
    inbound = finance_df[
        (finance_df["direction"] == "入库")
        & finance_df["record_id"].notna()
    ].copy()
    if inbound.empty:
        return pd.DataFrame()
    inbound["source_type"] = inbound["source_type"].map(
        SOURCE_LABELS
    ).fillna(inbound["source_type"])
    return inbound.rename(columns={
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
        "材质", "颜色", "尺码/型号", "数量", "单位成本",
    ]].sort_values(
        ["日期", "部门", "品类", "品牌", "材质", "颜色", "尺码/型号"],
        ascending=[False, True, True, True, True, True, True],
    ).reset_index(drop=True)
