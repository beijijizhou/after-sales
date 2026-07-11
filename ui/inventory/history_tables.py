import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
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
    st.dataframe(display_df, hide_index=True, use_container_width=True, column_config=column_config)
