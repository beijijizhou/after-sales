import pandas as pd
import streamlit as st

from ui.inventory.history_tables import format_date_columns


def add_movement_batch_key(movement_df):
    movement_df = format_date_columns(movement_df, ["movement_date"]).copy()
    movement_df["quantity_change"] = pd.to_numeric(
        movement_df["quantity_change"], errors="coerce"
    ).fillna(0).astype(int)
    movement_df["reason"] = movement_df.get("reason", "").fillna("").astype(str)
    movement_df["recorded_at"] = pd.to_datetime(movement_df["created_at"], errors="coerce")
    movement_df["recorded_key"] = movement_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
    movement_df["direction"] = movement_df["quantity_change"].apply(lambda value: "入库" if value > 0 else "出库")
    movement_df["batch_key"] = (
        "movement|"
        + movement_df["recorded_key"].fillna("")
        + "|"
        + movement_df["movement_date"].astype(str)
        + "|"
        + movement_df["department"].fillna("").astype(str)
        + "|"
        + movement_df["category"].fillna("").astype(str)
        + "|"
        + movement_df["direction"]
        + "|"
        + movement_df["reason"]
    )
    return movement_df


def add_sku_batch_key(sku_import_df):
    sku_import_df = format_date_columns(sku_import_df, ["import_date"]).copy()
    sku_import_df["initial_quantity"] = pd.to_numeric(
        sku_import_df["initial_quantity"], errors="coerce"
    ).fillna(0).astype(int)
    sku_import_df["recorded_at"] = pd.to_datetime(sku_import_df["created_at"], errors="coerce")
    sku_import_df["recorded_key"] = sku_import_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
    sku_import_df["batch_key"] = (
        "sku|"
        + sku_import_df["recorded_key"].fillna("")
        + "|"
        + sku_import_df["import_date"].astype(str)
        + "|"
        + sku_import_df["department"].fillna("").astype(str)
        + "|"
        + sku_import_df["category"].fillna("").astype(str)
    )
    return sku_import_df


def build_movement_batch_rows(movement_df):
    if movement_df.empty:
        return []

    movement_df = add_movement_batch_key(movement_df)
    grouped_df = (
        movement_df
        .groupby(
            ["batch_key", "recorded_key", "movement_date", "department", "category", "direction", "reason"],
            as_index=False,
        )
        .agg(quantity=("quantity_change", lambda values: int(values.abs().sum())))
    )
    return [
        {
            "batch_key": row["batch_key"],
            "类型": row["direction"],
            "记录时间": row["recorded_key"],
            "表格日期": row["movement_date"],
            "部门": row["department"],
            "品类": row["category"],
            "数量": row["quantity"],
            "备注": row["reason"],
        }
        for row in grouped_df.to_dict("records")
    ]


def build_sku_batch_rows(sku_import_df):
    if sku_import_df.empty:
        return []

    sku_import_df = add_sku_batch_key(sku_import_df)
    grouped_df = (
        sku_import_df
        .groupby(["batch_key", "recorded_key", "import_date", "department", "category"], as_index=False)
        .agg(quantity=("initial_quantity", "sum"))
    )
    return [
        {
            "batch_key": row["batch_key"],
            "类型": "新增 SKU",
            "记录时间": row["recorded_key"],
            "表格日期": row["import_date"],
            "部门": row["department"],
            "品类": row["category"],
            "数量": int(row["quantity"]),
            "备注": "",
        }
        for row in grouped_df.to_dict("records")
    ]


def build_movement_batches(movement_df, sku_import_df):
    batch_rows = build_movement_batch_rows(movement_df) + build_sku_batch_rows(sku_import_df)
    if not batch_rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(batch_rows)
        .sort_values(["记录时间", "表格日期"], ascending=[False, False])
        .reset_index(drop=True)
    )


def render_batch_selector(batch_df):
    if batch_df.empty:
        st.info("暂无库存表格记录")
        return None

    st.subheader("库存表格记录")
    options = batch_df["batch_key"].tolist()
    labels = {
        row["batch_key"]: (
            f"{row['记录时间']}｜{row['类型']}｜{row['表格日期']}｜"
            f"{row['部门']} {row['品类']}｜{row['数量']}"
        )
        for row in batch_df.to_dict("records")
    }
    selected_batch = st.selectbox(
        "选择库存表格记录",
        options,
        format_func=lambda value: labels.get(value, value),
        key="inventory_history_batch",
    )
    st.caption("输入时间｜类型｜出入库日期｜部门/品类｜总计")
    return selected_batch
