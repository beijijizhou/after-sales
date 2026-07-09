from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS, build_daily_movement_summary, load_inventory_movements
from db.inventory_sku import load_sku_imports


def format_date_columns(df, date_columns):
    if df.empty:
        return df

    formatted_df = df.copy()
    for column in date_columns:
        if column in formatted_df.columns:
            formatted_df[column] = pd.to_datetime(formatted_df[column], errors="coerce").dt.date
    return formatted_df


def render_movement_table(movement_df):
    st.subheader("库存变动历史")
    if movement_df.empty:
        st.info("暂无库存变动记录")
        return

    display_df = format_date_columns(movement_df, ["movement_date", "created_at"]).rename(columns={
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "size": "尺码",
        "quantity_change": "变动数量",
        "quantity_after": "变动后库存",
        "movement_date": "日期",
        "reason": "备注",
        "created_at": "记录日期",
    })
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            "记录日期": st.column_config.DateColumn("记录日期"),
        },
    )


def render_sku_import_table(sku_import_df):
    st.subheader("SKU 导入历史")
    if sku_import_df.empty:
        st.info("暂无 SKU 导入记录")
        return

    import_df = format_date_columns(sku_import_df, ["import_date"])
    display_df = (
        import_df
        .pivot_table(
            index=["import_date", "brand", "material", "color"],
            columns="size",
            values="initial_quantity",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={
            "import_date": "日期",
            "brand": "品牌",
            "material": "材质",
            "color": "颜色",
        })
    )
    for size in SIZE_COLUMNS:
        if size not in display_df.columns:
            display_df[size] = 0
    display_df = display_df[["日期", "品牌", "材质", "颜色", *SIZE_COLUMNS]]
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            **{size: st.column_config.NumberColumn(size) for size in SIZE_COLUMNS},
        },
    )


def render_daily_movement_summary(movement_df):
    st.subheader("每日入库 / 消耗")
    daily_df = format_date_columns(build_daily_movement_summary(movement_df), ["日期"])
    if daily_df.empty:
        st.info("暂无每日库存变动")
        return

    st.dataframe(
        daily_df, hide_index=True, use_container_width=True,
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            "入库": st.column_config.NumberColumn("入库"),
            "消耗": st.column_config.NumberColumn("消耗"),
            "净变动": st.column_config.NumberColumn("净变动"),
        },
    )


def get_history_date(movement_df, sku_import_df):
    movement_dates = format_date_columns(movement_df, ["movement_date"]).get("movement_date", pd.Series(dtype=object))
    sku_dates = format_date_columns(sku_import_df, ["import_date"]).get("import_date", pd.Series(dtype=object))
    available_dates = sorted(
        set(movement_dates.dropna().tolist()) | set(sku_dates.dropna().tolist()),
        reverse=True,
    )
    today = datetime.now(ZoneInfo("America/New_York")).date()
    default_date = today if today in available_dates else available_dates[0] if available_dates else today
    return st.date_input("选择历史日期", value=default_date, key="inventory_history_date")


def render_inventory_history(supabase, department, category):
    movement_df = load_inventory_movements(supabase, department, category, limit=500)
    sku_import_df = load_sku_imports(supabase, department, category, limit=500)
    selected_date = get_history_date(movement_df, sku_import_df)
    dated_movement_df = format_date_columns(movement_df, ["movement_date"])
    dated_sku_import_df = format_date_columns(sku_import_df, ["import_date"])
    if not dated_movement_df.empty:
        dated_movement_df = dated_movement_df[dated_movement_df["movement_date"] == selected_date]
    if not dated_sku_import_df.empty:
        dated_sku_import_df = dated_sku_import_df[dated_sku_import_df["import_date"] == selected_date]

    render_daily_movement_summary(movement_df)
    render_movement_table(dated_movement_df)
    render_sku_import_table(dated_sku_import_df)
