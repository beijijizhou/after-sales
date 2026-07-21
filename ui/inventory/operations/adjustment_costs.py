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

    sku_signature = "|".join(cost_df[SKU_COLUMN].astype(str))
    signature = hashlib.sha256(sku_signature.encode("utf-8")).hexdigest()[:10]
    column_config = {
        ROW_COLUMN: None,
        SKU_COLUMN: st.column_config.TextColumn("SKU", disabled=True),
        **{
            size: st.column_config.NumberColumn(
                size, min_value=0.0, step=0.0001, format="%.4f"
            )
            for size in SIZE_COLUMNS
        },
    }
    st.markdown(f"#### {t('各尺码单价')}")
    edited_costs = st.data_editor(
        cost_df,
        hide_index=True,
        width="stretch",
        disabled=[ROW_COLUMN, SKU_COLUMN],
        column_config=column_config,
        key=f"{key}_{len(cost_df)}_{signature}",
    )
    return normalize_size_costs(edited_costs)


def build_size_cost_table(quantity_df):
    if quantity_df.empty:
        return pd.DataFrame(columns=[ROW_COLUMN, SKU_COLUMN, *SIZE_COLUMNS])

    source_df = pd.DataFrame(quantity_df).reset_index(drop=True)
    identities = pd.DataFrame({ROW_COLUMN: range(1, len(source_df) + 1)})
    identities[SKU_COLUMN] = source_df.apply(_format_sku, axis=1)
    for size in SIZE_COLUMNS:
        identities[size] = None
    return identities


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
    if cost_df is None or cost_df.empty:
        st.metric(t("当前编辑总件数"), f"{int(total):,}")
        return

    quantities = _long_quantities(quantity_df)
    amount_df = quantities.merge(
        cost_df, on=[ROW_COLUMN, "尺码"], how="left"
    )
    amount = (amount_df["数量"] * amount_df["成本"].fillna(0)).sum()
    count_col, amount_col = st.columns(2)
    count_col.metric(t("当前编辑总件数"), f"{int(total):,}")
    amount_col.metric(t("本次进货总金额"), f"{amount:,.2f}")


def _long_quantities(quantity_df):
    result = pd.DataFrame(quantity_df).copy()
    result[ROW_COLUMN] = range(1, len(result) + 1)
    long_df = result.melt(
        id_vars=[ROW_COLUMN],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    long_df["数量"] = pd.to_numeric(long_df["数量"], errors="coerce").fillna(0)
    return long_df
