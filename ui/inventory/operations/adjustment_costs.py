import hashlib

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t


IDENTITY_COLUMNS = ["日期", "品牌", "材质", "颜色"]
ROW_COLUMN = "入库行"
SKU_COLUMN = "SKU"


def render_size_cost_editor(quantity_df, key):
    cost_df = build_size_cost_table(quantity_df)
    if cost_df.empty:
        return pd.DataFrame(columns=[ROW_COLUMN, "尺码", "成本"])

    sku_signature = "|".join(
        cost_df[[ROW_COLUMN, SKU_COLUMN, "尺码"]]
        .astype(str)
        .agg("·".join, axis=1)
    )
    signature = hashlib.sha256(sku_signature.encode("utf-8")).hexdigest()[:10]
    column_config = {
        ROW_COLUMN: None,
        SKU_COLUMN: st.column_config.TextColumn("SKU", disabled=True),
        "尺码": st.column_config.TextColumn("尺码", disabled=True),
        "数量": st.column_config.NumberColumn(
            "数量", format="%d", disabled=True
        ),
        "成本": st.column_config.NumberColumn(
            "单价", min_value=0.0, step=0.0001, format="%.4f"
        ),
    }
    st.markdown(f"#### {t('各尺码单价')}")
    edited_costs = st.data_editor(
        cost_df,
        hide_index=True,
        width="stretch",
        disabled=[ROW_COLUMN, SKU_COLUMN, "尺码", "数量"],
        column_config=column_config,
        key=f"{key}_{len(cost_df)}_{signature}",
    )
    return normalize_size_costs(edited_costs)


def build_size_cost_table(quantity_df):
    if quantity_df.empty:
        return pd.DataFrame(columns=[
            ROW_COLUMN, SKU_COLUMN, "尺码", "数量", "成本",
        ])

    source_df = pd.DataFrame(quantity_df).reset_index(drop=True)
    quantities = _long_quantities(source_df)
    quantities = quantities[quantities["数量"] > 0].copy()
    sku_by_row = {
        index + 1: _format_sku(row)
        for index, row in source_df.iterrows()
    }
    quantities[SKU_COLUMN] = quantities[ROW_COLUMN].map(sku_by_row)
    quantities["成本"] = None
    return quantities[[
        ROW_COLUMN, SKU_COLUMN, "尺码", "数量", "成本",
    ]].reset_index(drop=True)


def _format_sku(row):
    values = [
        row.get(column, "")
        for column in ["品类", "品牌", "材质", "颜色"]
        if str(row.get(column, "")).strip()
    ]
    return " · ".join(str(value).strip() for value in values)


def normalize_size_costs(cost_df):
    if cost_df.empty:
        return pd.DataFrame(columns=[ROW_COLUMN, "尺码", "成本"])
    result = pd.DataFrame(cost_df).copy()
    if {"尺码", "成本"}.issubset(result.columns):
        result["成本"] = pd.to_numeric(result["成本"], errors="coerce")
        return result[[ROW_COLUMN, "尺码", "成本"]].dropna(
            subset=["成本"]
        ).reset_index(drop=True)
    long_df = result.melt(
        id_vars=[ROW_COLUMN],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="成本",
    )
    long_df["成本"] = pd.to_numeric(long_df["成本"], errors="coerce")
    return long_df.dropna(subset=["成本"]).reset_index(drop=True)


def apply_size_costs(adjustment_df, cost_df):
    if adjustment_df.empty:
        return adjustment_df
    if cost_df is None or cost_df.empty:
        return adjustment_df.drop(columns=[ROW_COLUMN], errors="ignore")
    keys = [ROW_COLUMN, "尺码"]
    result = adjustment_df.merge(
        cost_df.rename(columns={"成本": "尺码成本"}), on=keys, how="left"
    )
    result["成本"] = result["尺码成本"].combine_first(result["成本"])
    return result.drop(columns=["尺码成本", ROW_COLUMN])


def render_adjustment_totals(quantity_df, cost_df=None):
    total = sum(
        pd.to_numeric(quantity_df.get(size, 0), errors="coerce").fillna(0).sum()
        for size in SIZE_COLUMNS
    )
    if cost_df is None:
        st.metric(t("当前编辑总件数"), f"{int(total):,}")
        return
    breakdown = build_adjustment_cost_breakdown(quantity_df, cost_df)
    missing = breakdown[breakdown["单价"].isna()]
    amount = breakdown["小计"].sum(min_count=1)
    count_col, amount_col = st.columns(2)
    count_col.metric(t("当前编辑总件数"), f"{int(total):,}")
    if breakdown.empty or not missing.empty:
        amount_col.metric(t("本次进货总金额"), "待补成本")
    else:
        amount_col.metric(t("本次进货总金额"), f"{amount:,.2f}")
    if breakdown.empty:
        return
    if not missing.empty:
        missing_quantity = int(missing["数量"].sum())
        st.warning(
            f"还有 {len(missing):,} 个尺码、{missing_quantity:,} 件"
            "没有填写单价；当前不能计算完整进货总金额。"
        )
    st.dataframe(
        breakdown,
        hide_index=True,
        width="stretch",
        column_config={
            ROW_COLUMN: None,
            "数量": st.column_config.NumberColumn(format="%d"),
            "单价": st.column_config.NumberColumn(format="%.4f"),
            "小计": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def build_adjustment_cost_breakdown(quantity_df, cost_df):
    quantities = _long_quantities(quantity_df)
    if quantities.empty:
        return pd.DataFrame(columns=[
            ROW_COLUMN, SKU_COLUMN, "尺码", "数量", "单价", "小计",
        ])
    source = pd.DataFrame(quantity_df).reset_index(drop=True)
    sku_by_row = {
        index + 1: _format_sku(row)
        for index, row in source.iterrows()
    }
    quantities[SKU_COLUMN] = quantities[ROW_COLUMN].map(sku_by_row)
    quantities = quantities[quantities["数量"] > 0].copy()
    normalized_costs = pd.DataFrame(cost_df).rename(
        columns={"成本": "单价"}
    )
    if normalized_costs.empty:
        normalized_costs = pd.DataFrame(
            columns=[ROW_COLUMN, "尺码", "单价"]
        )
    result = quantities.merge(
        normalized_costs[[ROW_COLUMN, "尺码", "单价"]],
        on=[ROW_COLUMN, "尺码"],
        how="left",
    )
    result["单价"] = pd.to_numeric(result["单价"], errors="coerce")
    result["小计"] = result["数量"] * result["单价"]
    return result[[
        ROW_COLUMN, SKU_COLUMN, "尺码", "数量", "单价", "小计",
    ]].reset_index(drop=True)


def _long_quantities(quantity_df):
    result = pd.DataFrame(quantity_df).copy()
    result[ROW_COLUMN] = range(1, len(result) + 1)
    for size in SIZE_COLUMNS:
        if size not in result.columns:
            result[size] = 0
    long_df = result.melt(
        id_vars=[ROW_COLUMN],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    long_df["数量"] = pd.to_numeric(long_df["数量"], errors="coerce").fillna(0)
    return long_df
