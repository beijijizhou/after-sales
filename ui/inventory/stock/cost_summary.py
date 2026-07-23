import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.core.costs import update_inventory_unit_costs
from ui.inventory.i18n import t
from ui.inventory.operations.adjustment_costs import (
    ROW_COLUMN,
    render_size_cost_editor,
)


def build_inventory_cost_table(inventory_df):
    if inventory_df.empty or "成本" not in inventory_df.columns:
        return pd.DataFrame()

    cost_df = inventory_df.copy()
    if "型号" in cost_df.columns:
        cost_df = cost_df.rename(columns={
            "成本": "单位成本", "总库存": "库存数量"
        })
        cost_df["单位成本"] = pd.to_numeric(
            cost_df["单位成本"], errors="coerce"
        ).fillna(0)
        cost_df["库存数量"] = pd.to_numeric(
            cost_df["库存数量"], errors="coerce"
        ).fillna(0).astype(int)
        cost_df = cost_df[
            (cost_df["单位成本"] > 0) & (cost_df["库存数量"] != 0)
        ]
        if cost_df.empty:
            return pd.DataFrame()
        cost_df["库存金额"] = cost_df["库存数量"] * cost_df["单位成本"]
        columns = [
            "品类", "品牌", "材质", "颜色", "型号", "单位成本",
            "库存数量", "库存金额",
        ]
        return cost_df[columns].sort_values(
            "库存金额", ascending=False
        ).reset_index(drop=True)

    size_columns = [column for column in SIZE_COLUMNS if column in cost_df.columns]
    for column in size_columns:
        cost_df[column] = pd.to_numeric(cost_df[column], errors="coerce").fillna(0)
    cost_df["单位成本"] = pd.to_numeric(
        cost_df["成本"], errors="coerce"
    ).fillna(0)
    cost_df = cost_df[cost_df["单位成本"] > 0]
    if cost_df.empty:
        return pd.DataFrame()
    identity_columns = [
        column for column in ["品类", "品牌", "材质", "颜色", "单位成本"]
        if column in cost_df.columns
    ]
    cost_df = cost_df.melt(
        id_vars=identity_columns,
        value_vars=size_columns,
        var_name="尺码",
        value_name="库存数量",
    )
    cost_df["库存数量"] = pd.to_numeric(
        cost_df["库存数量"], errors="coerce"
    ).fillna(0).astype(int)
    cost_df = cost_df[cost_df["库存数量"] != 0]
    cost_df["库存金额"] = cost_df["库存数量"] * cost_df["单位成本"]

    return (
        cost_df.groupby([*identity_columns, "尺码"], dropna=False, as_index=False)
        .agg(库存数量=("库存数量", "sum"), 库存金额=("库存金额", "sum"))
        .sort_values("库存金额", ascending=False)
        .reset_index(drop=True)
    )


def render_inventory_cost_summary(
    supabase, department, category, inventory_df, raw_inventory_df
):
    st.subheader(t("当前库存成本"))
    saved_message = st.session_state.pop("inventory_cost_saved_message", None)
    if saved_message:
        st.success(saved_message)
    cost_df = build_inventory_cost_table(inventory_df)
    if cost_df.empty:
        st.info(t("暂无库存成本数据"))
    else:
        total_cost = float(cost_df["库存金额"].sum())
        st.metric(t("当前库存总成本"), f"${total_cost:,.2f}")
        _render_cost_table(cost_df)

    _render_missing_costs(
        supabase, department, category, raw_inventory_df
    )


def _render_cost_table(cost_df):
    st.dataframe(
        cost_df, hide_index=True, width="stretch",
        column_config={
            "品类": st.column_config.TextColumn(t("品类")),
            "品牌": st.column_config.TextColumn(t("品牌")),
            "材质": st.column_config.TextColumn(t("材质")),
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t("尺码")),
            "型号": st.column_config.TextColumn(t("型号")),
            "单位成本": st.column_config.NumberColumn(
                t("单位成本"), format="$%.4f"
            ),
            "库存数量": st.column_config.NumberColumn(t("库存数量"), format="%d"),
            "库存金额": st.column_config.NumberColumn(t("库存金额"), format="$%.2f"),
        },
    )


def _render_missing_costs(supabase, department, category, raw_df):
    missing_df = _missing_cost_inventory(raw_df)
    if missing_df.empty:
        return

    st.divider()
    st.subheader(t("未填写成本库存"))
    if _uses_models(missing_df):
        _render_missing_model_costs(
            supabase, department, category, missing_df, raw_df
        )
        return
    st.dataframe(
        missing_df[["品牌", "材质"]].drop_duplicates().reset_index(drop=True),
        hide_index=True,
        width="stretch",
    )
    sku_df = missing_df[
        ["品类", "品牌", "材质", "颜色"]
    ].drop_duplicates().reset_index(drop=True)
    version = st.session_state.get("inventory_cost_editor_version", 0)
    edited_costs = render_size_cost_editor(sku_df, f"missing_costs_{version}")
    if st.button(t("保存库存成本"), width="stretch"):
        cost_updates = _attach_cost_identities(sku_df, edited_costs)
        updated = update_inventory_unit_costs(
            supabase, department, category, cost_updates, raw_df
        )
        if not updated:
            st.warning(t("请先填写有效成本"))
            return
        st.session_state["inventory_cost_saved_message"] = t(
            "库存成本已更新"
        ).format(count=updated)
        st.session_state["inventory_cost_editor_version"] = version + 1
        st.rerun()


def _render_missing_model_costs(
    supabase, department, category, missing_df, raw_df
):
    sku_df = (
        missing_df[["品类", "品牌", "材质", "颜色", "size"]]
        .drop_duplicates()
        .rename(columns={"size": "型号"})
        .reset_index(drop=True)
    )
    sku_df["成本"] = None
    version = st.session_state.get("inventory_model_cost_version", 0)
    edited = pd.DataFrame(st.data_editor(
        sku_df, hide_index=True, width="stretch",
        disabled=["品类", "品牌", "材质", "颜色", "型号"],
        column_config={
            "品类": st.column_config.TextColumn(t("品类")),
            "品牌": st.column_config.TextColumn(t("品牌")),
            "材质": st.column_config.TextColumn(t("材质")),
            "颜色": st.column_config.TextColumn(t("颜色")),
            "型号": st.column_config.TextColumn(t("型号")),
            "成本": st.column_config.NumberColumn(
                t("成本"), min_value=0.0, step=0.0001, format="%.4f"
            ),
        },
        key=f"inventory_model_cost_{version}",
    ))
    if not st.button(t("保存库存成本"), width="stretch"):
        return
    cost_updates = edited.rename(columns={"型号": "尺码"})
    updated = update_inventory_unit_costs(
        supabase, department, category, cost_updates, raw_df
    )
    if not updated:
        st.warning(t("请先填写有效成本"))
        return
    st.session_state["inventory_cost_saved_message"] = t(
        "库存成本已更新"
    ).format(count=updated)
    st.session_state["inventory_model_cost_version"] = version + 1
    st.rerun()


def _uses_models(df):
    values = {
        str(value).strip().upper() for value in df.get("size", [])
        if pd.notna(value) and str(value).strip()
    }
    return bool(values - set(SIZE_COLUMNS))


def _missing_cost_inventory(raw_df):
    if raw_df.empty:
        return raw_df
    result = raw_df.copy()
    result["unit_cost"] = pd.to_numeric(result["unit_cost"], errors="coerce").fillna(0)
    result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce").fillna(0)
    result = result[(result["unit_cost"] <= 0) & (result["quantity"] > 0)]
    return result.rename(columns={
        "category": "品类", "brand": "品牌", "material": "材质", "color": "颜色"
    })


def _attach_cost_identities(sku_df, cost_df):
    identities = sku_df.copy()
    identities[ROW_COLUMN] = range(1, len(identities) + 1)
    return cost_df.merge(identities, on=ROW_COLUMN, how="left")
