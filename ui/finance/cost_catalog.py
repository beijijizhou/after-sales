"""Unified SKU cost overview and inbound price history."""

from hashlib import sha1

import pandas as pd
import streamlit as st

from ui.finance.reports import render_inventory_filters
from ui.table_layout import fit_table_height
from utils.sku_sorting import sort_sku_rows


IDENTITY = ["department", "category", "brand", "material", "color", "size"]
DISPLAY_IDENTITY = {
    "department": "部门", "category": "品类", "brand": "品牌",
    "material": "材质", "color": "颜色", "size": "尺码/型号",
}
SOURCE_LABELS = {
    "opening": "初始化库存", "bulk": "正常入库", "transfer": "临时调货",
    "consumable_inbound": "耗材入库",
    "consumable_adjustment": "耗材库存修正",
}


def build_sku_cost_overview(value_df, history_df):
    values = _normalize_identity(value_df)
    history = _normalize_identity(history_df)
    value_summary = _value_summary(values)
    history_summary = _history_summary(history)
    if value_summary.empty and history_summary.empty:
        return pd.DataFrame()
    overview = value_summary.merge(
        history_summary, on=IDENTITY, how="outer"
    )
    numeric_defaults = {
        "inventory_quantity": 0, "tracked_quantity": 0,
        "inventory_value": 0, "missing_cost_quantity": 0,
        "priced_batches": 0, "missing_batches": 0,
    }
    for column, default in numeric_defaults.items():
        overview[column] = pd.to_numeric(
            overview.get(column, default), errors="coerce"
        ).fillna(default)
    overview["priced_average_cost"] = (
        overview["inventory_value"]
        / overview["tracked_quantity"].replace(0, pd.NA)
    )
    overview["cost_status"] = "已填写"
    missing = (
        overview["missing_cost_quantity"].gt(0)
        | overview["missing_batches"].gt(0)
        | overview["priced_batches"].eq(0)
    )
    overview.loc[missing, "cost_status"] = "缺成本"
    varied = (
        ~missing
        & overview["min_cost"].notna()
        & overview["max_cost"].notna()
        & overview["min_cost"].sub(overview["max_cost"]).abs().gt(0.00005)
    )
    overview.loc[varied, "cost_status"] = "多批次价格"
    overview["sku_key"] = _identity_keys(overview)
    return overview.reset_index(drop=True)


def render_sku_cost_catalog(value_df, history_df):
    st.subheader("全部 SKU 成本台账")
    st.caption(
        "这里显示所有 SKU 的当前计价均价、最近入库价和历史价格范围；"
        "选择一个 SKU 可以查看每个入库批次的价格。"
    )
    overview = build_sku_cost_overview(value_df, history_df)
    if overview.empty:
        st.info("目前还没有 SKU 成本资料。")
        return pd.DataFrame(history_df)
    filtered = render_inventory_filters(
        overview, key="finance_cost_catalog_filters"
    )
    status = st.segmented_control(
        "成本状态", ["全部 SKU", "仅缺成本", "已填写"],
        default="全部 SKU", key="finance_cost_catalog_status",
    ) or "全部 SKU"
    if status == "仅缺成本":
        filtered = filtered[filtered["cost_status"] == "缺成本"]
    elif status == "已填写":
        filtered = filtered[filtered["cost_status"] != "缺成本"]
    filtered = _sort_overview(filtered)
    metrics = st.columns(3)
    metrics[0].metric("当前 SKU", f"{len(filtered):,}")
    metrics[1].metric(
        "缺成本 SKU",
        f"{int((filtered['cost_status'] == '缺成本').sum()):,}",
    )
    metrics[2].metric(
        "缺成本库存",
        f"{int(filtered['missing_cost_quantity'].sum()):,}",
    )
    display = _overview_display(filtered)
    st.dataframe(
        display, hide_index=True, width="stretch",
        height=fit_table_height(display),
        column_config={
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "已计价库存均价": st.column_config.NumberColumn(format="$%.4f"),
            "最近入库价": st.column_config.NumberColumn(format="$%.4f"),
            "历史最低价": st.column_config.NumberColumn(format="$%.4f"),
            "历史最高价": st.column_config.NumberColumn(format="$%.4f"),
            "缺成本库存": st.column_config.NumberColumn(format="%d"),
        },
    )
    if filtered.empty:
        return pd.DataFrame(history_df).iloc[0:0]
    options = filtered["sku_key"].tolist()
    labels = {
        row["sku_key"]: "｜".join(
            str(row[column] or "—") for column in IDENTITY
        )
        for row in filtered.to_dict("records")
    }
    selected = st.selectbox(
        "选择 SKU 查看历史价格", options,
        format_func=lambda value: labels.get(value, value),
        key="finance_cost_history_sku",
    )
    scoped_history = filter_cost_history_to_skus(history_df, filtered)
    detail = build_sku_cost_history(scoped_history, selected)
    st.markdown("#### SKU 历史入库价格")
    if detail.empty:
        st.info("这个 SKU 暂无入库成本记录。")
    else:
        st.dataframe(
            detail, hide_index=True, width="stretch",
            height=fit_table_height(detail),
            column_config={
                "数量": st.column_config.NumberColumn(format="%d"),
                "单位成本": st.column_config.NumberColumn(format="$%.4f"),
            },
        )
    return scoped_history


def filter_cost_history_to_skus(history_df, overview_df):
    history = _normalize_identity(history_df)
    overview = _normalize_identity(overview_df)
    if history.empty or overview.empty:
        return history.iloc[0:0]
    keys = set(_identity_keys(overview))
    return history[_identity_keys(history).isin(keys)].reset_index(drop=True)


def build_sku_cost_history(history_df, sku_key):
    history = _normalize_identity(history_df)
    if history.empty:
        return pd.DataFrame()
    rows = history[_identity_keys(history) == str(sku_key)].copy()
    if rows.empty:
        return pd.DataFrame()
    costs = pd.to_numeric(rows["unit_cost"], errors="coerce")
    rows["成本状态"] = (
        costs.isna() | costs.le(0)
    ).map({True: "缺成本", False: "已填写"})
    rows["批次"] = rows.get(
        "business_batch_label", pd.Series("", index=rows.index)
    ).fillna("").astype(str)
    fallback = rows.get(
        "batch_id", pd.Series("", index=rows.index)
    ).fillna("").astype(str)
    fallback = fallback.where(
        fallback.str.strip() != "",
        rows.get("record_id", pd.Series("", index=rows.index)).astype(str),
    )
    rows["批次"] = rows["批次"].where(
        rows["批次"].str.strip() != "", fallback
    )
    rows["来源"] = rows["source_type"].map(SOURCE_LABELS).fillna(
        rows["source_type"]
    )
    rows["日期"] = pd.to_datetime(rows["date"], errors="coerce").dt.date
    rows["数量"] = pd.to_numeric(rows["quantity"], errors="coerce").fillna(0)
    rows["单位成本"] = costs
    return rows.sort_values(
        ["日期", "recorded_at"], ascending=[False, False], na_position="last"
    )[["日期", "批次", "来源", "数量", "单位成本", "成本状态"]].reset_index(
        drop=True
    )


def _value_summary(values):
    if values.empty:
        return pd.DataFrame(columns=IDENTITY)
    for column in [
        "inventory_quantity", "tracked_quantity", "inventory_value",
        "missing_cost_quantity",
    ]:
        values[column] = pd.to_numeric(
            values.get(column, 0), errors="coerce"
        ).fillna(0)
    return values.groupby(IDENTITY, as_index=False, dropna=False).agg(
        inventory_quantity=("inventory_quantity", "sum"),
        tracked_quantity=("tracked_quantity", "sum"),
        inventory_value=("inventory_value", "sum"),
        missing_cost_quantity=("missing_cost_quantity", "sum"),
    )


def _history_summary(history):
    if history.empty:
        return pd.DataFrame(columns=IDENTITY)
    data = history[history.get("direction", "入库") == "入库"].copy()
    data["_cost"] = pd.to_numeric(data["unit_cost"], errors="coerce")
    data["_missing"] = data["_cost"].isna() | data["_cost"].le(0)
    data["_priced"] = (~data["_missing"]).astype(int)
    data["_valid_cost"] = data["_cost"].where(~data["_missing"])
    data["_sort_date"] = pd.to_datetime(data["date"], errors="coerce")
    data["_sort_recorded"] = pd.to_datetime(
        data.get("recorded_at"), errors="coerce", utc=True
    )
    latest = (
        data[~data["_missing"]]
        .sort_values(["_sort_date", "_sort_recorded"])
        .drop_duplicates(IDENTITY, keep="last")[IDENTITY + ["_cost"]]
        .rename(columns={"_cost": "latest_cost"})
    )
    summary = data.groupby(IDENTITY, as_index=False, dropna=False).agg(
        min_cost=("_valid_cost", "min"),
        max_cost=("_valid_cost", "max"),
        priced_batches=("_priced", "sum"),
        missing_batches=("_missing", "sum"),
    )
    return summary.merge(latest, on=IDENTITY, how="left")


def _overview_display(rows):
    display = rows.rename(columns={
        **DISPLAY_IDENTITY,
        "inventory_quantity": "当前库存",
        "priced_average_cost": "已计价库存均价",
        "latest_cost": "最近入库价",
        "min_cost": "历史最低价", "max_cost": "历史最高价",
        "missing_batches": "缺成本批次",
        "missing_cost_quantity": "缺成本库存",
        "cost_status": "状态",
    })
    return display[[
        "部门", "品类", "品牌", "材质", "颜色", "尺码/型号",
        "当前库存", "已计价库存均价", "最近入库价",
        "历史最低价", "历史最高价", "缺成本批次", "缺成本库存", "状态",
    ]]


def _sort_overview(rows):
    data = rows.copy()
    data["_missing_order"] = (data["cost_status"] != "缺成本").astype(int)
    return sort_sku_rows(
        data, material="material", color="color", size="size",
        leading=["_missing_order", "department", "category"],
    ).drop(columns=["_missing_order"]).reset_index(drop=True)


def _normalize_identity(rows):
    data = pd.DataFrame(rows).copy()
    for column in IDENTITY:
        if column not in data:
            data[column] = ""
        data[column] = data[column].fillna("").astype(str)
    return data


def _identity_keys(rows):
    data = _normalize_identity(rows)
    joined = data[IDENTITY].agg("||".join, axis=1)
    return joined.map(lambda value: sha1(value.encode()).hexdigest()[:16])
