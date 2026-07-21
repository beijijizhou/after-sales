from datetime import datetime
import hashlib
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS, apply_adjustment_rows
from utils.auth import get_current_operator_name
from ui.inventory.i18n import t


LOCKED_COLUMNS = ["品类", "品牌", "材质", "颜色", "成本"]


def render_inventory_table_editor(
    supabase,
    department,
    category,
    display_df,
    column_config,
    table_height,
):
    original_df = display_df.drop(columns=["总库存"], errors="ignore").reset_index(drop=True)
    version = st.session_state.get("inventory_inline_editor_version", 0)
    identity_columns = [
        column for column in LOCKED_COLUMNS if column in original_df.columns
    ]
    identity = original_df[identity_columns].fillna("").astype(str).to_csv(index=False)
    signature = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    editor_config = dict(column_config)
    for size in SIZE_COLUMNS:
        if size in original_df.columns:
            editor_config[size] = st.column_config.NumberColumn(
                size, min_value=0, step=1, format="%d"
            )
    edited_df = st.data_editor(
        original_df,
        hide_index=True,
        width="stretch",
        disabled=[column for column in LOCKED_COLUMNS if column in original_df.columns],
        column_config=editor_config,
        height=table_height,
        key=f"inventory_inline_editor_{category}_{version}_{signature}",
    )
    edited_df = pd.DataFrame(edited_df)
    visible_sizes = [size for size in SIZE_COLUMNS if size in edited_df.columns]
    visible_total = sum(
        pd.to_numeric(edited_df[size], errors="coerce").fillna(0).sum()
        for size in visible_sizes
    )
    st.caption(f"{t('当前显示尺码合计')}: {int(visible_total):,} {t('件')}")

    if st.button(t("保存库存明细修改"), width="stretch"):
        adjustment_df = build_inline_adjustments(original_df, edited_df)
        if adjustment_df.empty:
            st.info(t("库存数量没有变化"))
            return
        username = get_current_operator_name()
        try:
            apply_adjustment_rows(
                supabase, department, category, adjustment_df, username
            )
        except Exception as error:
            st.error(f"{t('库存保存失败')}: {error}")
            return
        st.session_state["inventory_saved_message"] = (
            t("已保存库存修改").format(count=len(adjustment_df))
        )
        st.session_state["inventory_inline_editor_version"] = version + 1
        st.rerun()


def build_inline_adjustments(original_df, edited_df):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = []
    for index, original in original_df.iterrows():
        edited = edited_df.iloc[index]
        for size in SIZE_COLUMNS:
            if size not in edited_df.columns:
                continue
            old_quantity = clean_quantity(original.get(size, 0))
            new_quantity = clean_quantity(edited.get(size, 0))
            difference = new_quantity - old_quantity
            if difference == 0:
                continue
            rows.append({
                "日期": today,
                "操作": "增加" if difference > 0 else "扣减",
                "品牌": original.get("品牌", ""),
                "材质": original.get("材质", ""),
                "颜色": original.get("颜色", ""),
                "尺码": size,
                "数量": abs(difference),
                "成本": pd.NA,
                "备注": "库存明细直接编辑",
            })
    return pd.DataFrame(rows)


def clean_quantity(value):
    quantity = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(quantity) else max(int(quantity), 0)
