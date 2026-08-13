import pandas as pd
import streamlit as st

from ui.consumables.units import entry_unit, to_entry_quantity


def filter_items(items_df, categories, brands, search_text, active_mode):
    result = items_df.copy()
    if categories:
        result = result[result["category"].isin(categories)]
    if brands:
        result = result[result["brand"].isin(brands)]
    if search_text:
        needle = search_text.strip().lower()
        searchable = (
            result["name"].fillna("").astype(str)
            + " " + result["specification"].fillna("").astype(str)
        ).str.lower()
        result = result[searchable.str.contains(needle, regex=False)]
    if active_mode == "仅启用":
        result = result[result["is_active"] == True]
    elif active_mode == "仅停用":
        result = result[result["is_active"] == False]
    return result.reset_index(drop=True)


def render_stock(items_df, latest_costs, show_cost):
    if items_df.empty:
        st.info("当前筛选条件下没有耗材 SKU")
        return

    quantities = pd.to_numeric(
        items_df["current_quantity"], errors="coerce"
    ).fillna(0)
    minimums = pd.to_numeric(items_df["minimum_quantity"], errors="coerce")
    low_mask = minimums.notna() & (quantities <= minimums)

    col1, col2, col3 = st.columns(3)
    col1.metric("耗材 SKU", f"{len(items_df):,}")
    col2.metric("低库存", f"{int(low_mask.sum()):,}")
    col3.metric("已停用", f"{int((items_df['is_active'] == False).sum()):,}")

    display = items_df.copy()
    display["库存状态"] = "正常"
    display.loc[low_mask, "库存状态"] = "需要补货"
    display["包装换算"] = display.apply(_package_label, axis=1)
    display["当前库存"] = display.apply(
        lambda row: to_entry_quantity(row["current_quantity"], row), axis=1
    )
    display["计数单位"] = display.apply(entry_unit, axis=1)
    display["最低库存"] = display.apply(
        lambda row: to_entry_quantity(row["minimum_quantity"], row), axis=1
    )
    display = display.rename(columns={
        "category": "分类", "name": "耗材名称",
        "specification": "规格/型号", "brand": "品牌",
        "base_unit": "基础单位", "is_active": "状态",
    })
    display["状态"] = display["状态"].map({True: "启用", False: "停用"})

    columns = [
        "库存状态", "分类", "耗材名称", "规格/型号", "品牌",
        "当前库存", "计数单位", "包装换算", "最低库存", "状态",
    ]
    if show_cost:
        display["最近入库成本"] = display["id"].map(latest_costs)
        display["库存估值"] = (
            pd.to_numeric(display["current_quantity"], errors="coerce").fillna(0)
            * pd.to_numeric(display["最近入库成本"], errors="coerce").fillna(0)
        )
        columns.extend(["最近入库成本", "库存估值"])

    st.dataframe(
        display[columns],
        width="stretch",
        hide_index=True,
        column_config={
            "当前库存": st.column_config.NumberColumn(format="%.2f"),
            "最低库存": st.column_config.NumberColumn(format="%.2f"),
            "最近入库成本": st.column_config.NumberColumn(format="$%.4f"),
            "库存估值": st.column_config.NumberColumn(format="$%.2f"),
        },
    )


def build_latest_costs(movements_df):
    if movements_df.empty or "unit_cost" not in movements_df.columns:
        return {}
    priced = movements_df.copy()
    priced["unit_cost"] = pd.to_numeric(priced["unit_cost"], errors="coerce")
    priced = priced[priced["unit_cost"].notna()]
    if priced.empty:
        return {}
    priced["created_at"] = pd.to_datetime(
        priced["created_at"], errors="coerce", utc=True
    )
    priced = priced.sort_values("created_at", ascending=False)
    return (
        priced.drop_duplicates("item_id")
        .set_index("item_id")["unit_cost"]
        .to_dict()
    )


def _package_label(row):
    package = str(row.get("package_unit") or "").strip()
    quantity = row.get("units_per_package")
    if not package or pd.isna(quantity):
        return ""
    return f"1 {package} = {float(quantity):g} {row['base_unit']}"
