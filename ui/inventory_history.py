import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS, load_inventory_movements
from db.inventory_sku import load_sku_imports
from utils.auth import has_permission


def format_date_columns(df, date_columns):
    if df.empty:
        return df

    formatted_df = df.copy()
    for column in date_columns:
        if column in formatted_df.columns:
            formatted_df[column] = pd.to_datetime(formatted_df[column], errors="coerce").dt.date
    return formatted_df


def build_movement_detail_table(movement_df):
    if movement_df.empty:
        return pd.DataFrame()

    movement_df = format_date_columns(movement_df, ["movement_date", "created_at"]).copy()
    movement_df["quantity_change"] = pd.to_numeric(
        movement_df["quantity_change"], errors="coerce"
    ).fillna(0).astype(int)
    movement_df["reason"] = movement_df.get("reason", "").fillna("").astype(str)
    index_columns = ["movement_date", "department", "category", "brand", "material", "color", "reason"]
    display_df = (
        movement_df
        .pivot_table(
            index=index_columns,
            columns="size",
            values="quantity_change",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={
            "movement_date": "日期",
            "department": "部门",
            "category": "品类",
            "brand": "品牌",
            "material": "材质",
            "color": "颜色",
            "reason": "备注",
        })
    )
    for size in SIZE_COLUMNS:
        if size not in display_df.columns:
            display_df[size] = 0
        display_df[size] = pd.to_numeric(display_df[size], errors="coerce").fillna(0).astype(int)
    display_df["合计"] = display_df[SIZE_COLUMNS].sum(axis=1)
    return display_df[["日期", "部门", "品类", "品牌", "材质", "颜色", *SIZE_COLUMNS, "合计", "备注"]]


def render_movement_table(movement_df):
    st.subheader("库存变动明细")
    display_df = build_movement_detail_table(movement_df)
    if display_df.empty:
        st.info("暂无库存变动明细")
        return

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
            "合计": st.column_config.NumberColumn("合计", format="%d"),
        },
    )


def build_sku_import_detail_table(sku_import_df):
    if sku_import_df.empty:
        return pd.DataFrame()

    import_df = format_date_columns(sku_import_df, ["import_date"])
    include_cost = has_permission("can_view_cost")
    index_columns = ["import_date", "department", "category", "brand", "material", "color"]
    if include_cost:
        index_columns.append("unit_cost")
    display_df = (
        import_df
        .pivot_table(
            index=index_columns,
            columns="size",
            values="initial_quantity",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={
            "import_date": "日期",
            "department": "部门",
            "category": "品类",
            "brand": "品牌",
            "material": "材质",
            "color": "颜色",
            "unit_cost": "成本",
        })
    )
    for size in SIZE_COLUMNS:
        if size not in display_df.columns:
            display_df[size] = 0
    cost_columns = ["成本"] if include_cost else []
    optional_columns = [column for column in ["部门", "品类"] if column in display_df.columns]
    display_df = display_df[["日期", *optional_columns, "品牌", "材质", "颜色", *cost_columns, *SIZE_COLUMNS]]
    column_config = {
        "日期": st.column_config.DateColumn("日期"),
        **{size: st.column_config.NumberColumn(size) for size in SIZE_COLUMNS},
    }
    if "成本" in display_df.columns:
        column_config["成本"] = st.column_config.NumberColumn("成本", format="%.2f")

    return display_df, column_config


def render_sku_import_table(sku_import_df):
    st.subheader("SKU 导入明细")
    table_result = build_sku_import_detail_table(sku_import_df)
    if isinstance(table_result, pd.DataFrame) and table_result.empty:
        st.info("暂无 SKU 导入明细")
        return

    display_df, column_config = table_result

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config=column_config,
    )


def build_movement_batches(movement_df, sku_import_df):
    batch_rows = []
    movement_df = format_date_columns(movement_df, ["movement_date"])
    if not movement_df.empty:
        movement_df = movement_df.copy()
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
        grouped_df = (
            movement_df
            .groupby(
                ["batch_key", "recorded_key", "movement_date", "department", "category", "direction", "reason"],
                as_index=False,
            )
            .agg(quantity=("quantity_change", lambda values: int(values.abs().sum())))
        )
        for row in grouped_df.to_dict("records"):
            batch_rows.append({
                "batch_key": row["batch_key"],
                "类型": row["direction"],
                "记录时间": row["recorded_key"],
                "表格日期": row["movement_date"],
                "部门": row["department"],
                "品类": row["category"],
                "数量": row["quantity"],
                "备注": row["reason"],
            })

    sku_import_df = format_date_columns(sku_import_df, ["import_date"])
    if not sku_import_df.empty:
        sku_import_df = sku_import_df.copy()
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
        grouped_df = (
            sku_import_df
            .groupby(["batch_key", "recorded_key", "import_date", "department", "category"], as_index=False)
            .agg(quantity=("initial_quantity", "sum"))
        )
        for row in grouped_df.to_dict("records"):
            batch_rows.append({
                "batch_key": row["batch_key"],
                "类型": "新增 SKU",
                "记录时间": row["recorded_key"],
                "表格日期": row["import_date"],
                "部门": row["department"],
                "品类": row["category"],
                "数量": int(row["quantity"]),
                "备注": "",
            })

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


def render_inventory_history(supabase, department, category):
    movement_df = load_inventory_movements(supabase, department, "", limit=500)
    sku_import_df = load_sku_imports(supabase, department, "", limit=500)
    batch_df = build_movement_batches(movement_df, sku_import_df)
    selected_batch = render_batch_selector(batch_df)
    if not selected_batch:
        return

    dated_movement_df = format_date_columns(movement_df, ["movement_date"])
    dated_sku_import_df = format_date_columns(sku_import_df, ["import_date"])
    selected_batch_df = batch_df[batch_df["batch_key"] == selected_batch]
    selected_type = selected_batch_df.iloc[0]["类型"] if not selected_batch_df.empty else ""

    if selected_type == "新增 SKU":
        dated_sku_import_df = dated_sku_import_df.copy()
        dated_sku_import_df["recorded_at"] = pd.to_datetime(dated_sku_import_df["created_at"], errors="coerce")
        dated_sku_import_df["recorded_key"] = dated_sku_import_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
        dated_sku_import_df["batch_key"] = (
            "sku|"
            + dated_sku_import_df["recorded_key"].fillna("")
            + "|"
            + dated_sku_import_df["import_date"].astype(str)
            + "|"
            + dated_sku_import_df["department"].fillna("").astype(str)
            + "|"
            + dated_sku_import_df["category"].fillna("").astype(str)
        )
        render_sku_import_table(dated_sku_import_df[dated_sku_import_df["batch_key"] == selected_batch])
        return

    dated_movement_df = dated_movement_df.copy()
    dated_movement_df["quantity_change"] = pd.to_numeric(
        dated_movement_df["quantity_change"], errors="coerce"
    ).fillna(0).astype(int)
    dated_movement_df["reason"] = dated_movement_df.get("reason", "").fillna("").astype(str)
    dated_movement_df["recorded_at"] = pd.to_datetime(dated_movement_df["created_at"], errors="coerce")
    dated_movement_df["recorded_key"] = dated_movement_df["recorded_at"].dt.strftime("%Y-%m-%d %H:%M")
    dated_movement_df["direction"] = dated_movement_df["quantity_change"].apply(lambda value: "入库" if value > 0 else "出库")
    dated_movement_df["batch_key"] = (
        "movement|"
        + dated_movement_df["recorded_key"].fillna("")
        + "|"
        + dated_movement_df["movement_date"].astype(str)
        + "|"
        + dated_movement_df["department"].fillna("").astype(str)
        + "|"
        + dated_movement_df["category"].fillna("").astype(str)
        + "|"
        + dated_movement_df["direction"]
        + "|"
        + dated_movement_df["reason"]
    )

    render_movement_table(dated_movement_df[dated_movement_df["batch_key"] == selected_batch])
