import streamlit as st

from db.inventory import build_daily_movement_summary, load_inventory_movements
from db.inventory_sku import load_sku_imports


def render_movement_table(movement_df):
    st.subheader("库存变动历史")
    if movement_df.empty:
        st.info("暂无库存变动记录")
        return

    st.dataframe(movement_df.rename(columns={
        "材质": "材质",
        "color": "颜色",
        "size": "尺码",
        "quantity_change": "变动数量",
        "quantity_after": "变动后库存",
        "movement_date": "日期",
        "reason": "备注",
        "created_at": "时间",
    }), hide_index=True, use_container_width=True)


def render_sku_import_table(sku_import_df):
    st.subheader("SKU 导入历史")
    if sku_import_df.empty:
        st.info("暂无 SKU 导入记录")
        return

    st.dataframe(sku_import_df.rename(columns={
        "材质": "材质",
        "color": "颜色",
        "size": "尺码",
        "initial_quantity": "初始库存",
        "import_date": "日期",
        "created_at": "导入时间",
    }), hide_index=True, use_container_width=True)


def render_daily_movement_summary(movement_df):
    st.subheader("每日入库 / 消耗")
    daily_df = build_daily_movement_summary(movement_df)
    if daily_df.empty:
        st.info("暂无每日库存变动")
        return

    st.dataframe(
        daily_df, hide_index=True, use_container_width=True,
        column_config={
            "入库": st.column_config.NumberColumn("入库"),
            "消耗": st.column_config.NumberColumn("消耗"),
            "净变动": st.column_config.NumberColumn("净变动"),
        },
    )


def render_inventory_history(supabase):
    movement_df = load_inventory_movements(supabase, limit=500)
    render_daily_movement_summary(movement_df)
    render_movement_table(movement_df)
    render_sku_import_table(load_sku_imports(supabase, limit=500))
