import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t


def build_adjustment_preview(adjustment_df):
    if adjustment_df.empty:
        return pd.DataFrame()

    preview_df = adjustment_df.copy()
    for column in ["品牌", "材质", "颜色", "备注"]:
        preview_df[column] = preview_df[column].fillna("").astype(str)
    preview_df["数量"] = pd.to_numeric(
        preview_df["数量"], errors="coerce"
    ).fillna(0).astype(int)

    index_columns = ["日期", "操作", "品牌", "材质", "颜色", "备注"]
    wide_df = (
        preview_df
        .pivot_table(
            index=index_columns,
            columns="尺码",
            values="数量",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    for size in SIZE_COLUMNS:
        if size not in wide_df.columns:
            wide_df[size] = 0
        wide_df[size] = pd.to_numeric(wide_df[size], errors="coerce").fillna(0).astype(int)
    wide_df["合计"] = wide_df[SIZE_COLUMNS].sum(axis=1)
    return wide_df[[*index_columns[:-1], *SIZE_COLUMNS, "合计", "备注"]]


def render_adjustment_preview_editor(
    adjustment_df,
    key,
    lock_operation=False,
    lock_identity=False,
    allow_rows=True,
):
    preview_df = build_adjustment_preview(adjustment_df).drop(columns=["合计"])
    column_config = {
        "日期": st.column_config.DateColumn(t("日期"), required=True),
        "操作": st.column_config.SelectboxColumn(
            "操作", options=["增加", "扣减"], required=True
        ),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质"), required=True),
        "颜色": st.column_config.TextColumn(t("颜色"), required=True),
        "备注": st.column_config.TextColumn(t("备注")),
    }
    for size in SIZE_COLUMNS:
        column_config[size] = st.column_config.NumberColumn(
            size, min_value=0, step=1, format="%d"
        )
    disabled = ["操作"] if lock_operation else []
    if lock_identity:
        disabled.extend(["日期", "品牌", "材质", "颜色"])
    edited_df = st.data_editor(
        preview_df,
        hide_index=True,
        num_rows="dynamic" if allow_rows else "fixed",
        width="stretch",
        disabled=disabled,
        column_config=column_config,
        key=key,
    )
    total = sum(
        pd.to_numeric(edited_df[size], errors="coerce").fillna(0).sum()
        for size in SIZE_COLUMNS
    )
    st.caption(f"{t('当前编辑总件数')}: {int(total):,}")
    return edited_df
