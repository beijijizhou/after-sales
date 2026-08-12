"""Wide adjustment preview and correction editor."""

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t


def build_adjustment_preview(adjustment_df):
    if adjustment_df.empty:
        return pd.DataFrame()
    preview = adjustment_df.copy()
    preview["日期"] = pd.to_datetime(preview["日期"], errors="coerce").dt.date
    for column in ["品牌", "材质", "颜色", "备注"]:
        preview[column] = preview[column].fillna("").astype(str)
    preview["数量"] = pd.to_numeric(
        preview["数量"], errors="coerce"
    ).fillna(0).astype(int)
    index = ["日期", "操作", "品牌", "材质", "颜色", "备注"]
    wide = preview.pivot_table(
        index=index, columns="尺码", values="数量",
        aggfunc="sum", fill_value=0,
    ).reset_index()
    for size in SIZE_COLUMNS:
        if size not in wide:
            wide[size] = 0
        wide[size] = pd.to_numeric(
            wide[size], errors="coerce"
        ).fillna(0).astype(int)
    wide["合计"] = wide[SIZE_COLUMNS].sum(axis=1)
    return wide[[*index[:-1], *SIZE_COLUMNS, "合计", "备注"]]


def render_adjustment_preview_editor(
    adjustment_df, key, lock_operation=False, lock_identity=False,
    allow_rows=True, disabled_columns=None, fixed_date=None,
):
    preview = build_adjustment_preview(adjustment_df).drop(columns=["合计"])
    if fixed_date is not None:
        preview = preview.drop(columns=["日期"])
    config = {
        "操作": st.column_config.SelectboxColumn(
            "操作", options=["增加", "减少", "设置"], required=True
        ),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质"), required=True),
        "颜色": st.column_config.TextColumn(t("颜色"), required=True),
        "备注": st.column_config.TextColumn(t("备注")),
    }
    if fixed_date is None:
        config["日期"] = st.column_config.DateColumn(t("日期"), required=True)
    for size in SIZE_COLUMNS:
        config[size] = st.column_config.NumberColumn(
            size, min_value=0, step=1, format="%d"
        )
    disabled = ["操作"] if lock_operation else []
    if lock_identity:
        disabled.extend(["品牌", "材质", "颜色"])
        if fixed_date is None:
            disabled.append("日期")
    disabled.extend(disabled_columns or [])
    edited = st.data_editor(
        preview, hide_index=True,
        num_rows="dynamic" if allow_rows else "fixed", width="stretch",
        disabled=list(dict.fromkeys(disabled)), column_config=config, key=key,
    )
    total = sum(
        pd.to_numeric(edited[size], errors="coerce").fillna(0).sum()
        for size in SIZE_COLUMNS
    )
    if fixed_date is not None:
        edited.insert(0, "日期", fixed_date)
    st.caption(f"{t('当前编辑总件数')}: {int(total):,}")
    return edited
