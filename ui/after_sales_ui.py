import streamlit as st
import pandas as pd

from db.after_sale import save_after_sales_batch
from utils.auth import has_permission


AFTER_SALES_TYPES = ["短袖", "卫衣"]


def render_after_sales_section():
    st.divider()
    st.subheader("售后")

    df = st.session_state.get("search_df")

    if df is None:
        st.info("请先查询数据，再保存售后记录。")
        return

    if not has_permission("can_input_after_sales"):
        st.info("当前账号只能查看售后数据，不能保存售后记录")
        return

    editable_df = build_after_sales_editor_df(df)
    edited_df = st.data_editor(
        editable_df,
        hide_index=True,
        use_container_width=True,
        disabled=["barcode", "scanned_by", "scanned_at", "是否已售后"],
        column_config={
            "barcode": st.column_config.TextColumn("条码"),
            "scanned_by": st.column_config.TextColumn("质检人员"),
            "scanned_at": st.column_config.TextColumn("扫描时间"),
            "是否已售后": st.column_config.TextColumn("是否已售后"),
            "售后类型": st.column_config.SelectboxColumn("售后类型", options=AFTER_SALES_TYPES),
            "件数": st.column_config.NumberColumn("件数", min_value=1, step=1, format="%d"),
            "售后原因": st.column_config.TextColumn("售后原因"),
            "总金额": st.column_config.NumberColumn("总金额", min_value=0, step=0.01, format="%.2f"),
        },
        key="after_sales_editor",
    )

    if st.button("保存售后记录"):
        try:
            save_after_sales_batch(pd.DataFrame(edited_df))
        except Exception as e:
            st.error(f"保存售后失败：{e}")
            st.info("如果提示字段不存在，请先在 Supabase SQL Editor 运行 sql/after_sales_amount.sql")
            return

        st.success(f"已保存 {len(edited_df)} 个条码")


def build_after_sales_editor_df(df):
    display_columns = [
        "barcode", "scanned_by", "scanned_at",
        "是否已售后", "售后类型", "件数", "售后原因", "总金额",
    ]
    editor_df = df.copy()
    for column in display_columns:
        if column not in editor_df.columns:
            editor_df[column] = ""

    if "售后金额" in editor_df.columns and "总金额" not in editor_df.columns:
        editor_df["总金额"] = editor_df["售后金额"]
    editor_df["售后类型"] = editor_df["售后类型"].replace("", "短袖").fillna("短袖")
    editor_df["件数"] = pd.to_numeric(
        editor_df["件数"], errors="coerce"
    ).fillna(1).astype(int)
    editor_df["总金额"] = pd.to_numeric(
        editor_df["总金额"], errors="coerce"
    ).fillna(0)
    return editor_df[display_columns]
