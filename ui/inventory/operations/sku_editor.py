import hashlib

import pandas as pd
import streamlit as st

from db.inventory.sku_updates import (
    IDENTITY_COLUMNS,
    build_sku_identity_changes,
    build_sku_identity_table,
    update_sku_identities,
)
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name


def render_sku_catalog(inventory_df):
    st.subheader(t("现有 SKU"))
    source_df = build_sku_identity_table(inventory_df)
    if source_df.empty:
        st.info(t("暂无 SKU"))
        return

    st.metric(t("SKU 组合数"), len(source_df))
    display_df = source_df.drop(columns=["当前 SKU"])
    item_label = _item_label(inventory_df)
    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        height=min(max((len(source_df) + 1) * 35 + 8, 220), 800),
        column_config={
            "品类": st.column_config.TextColumn(t("品类")),
            "品牌": st.column_config.TextColumn(t("品牌")),
            "材质": st.column_config.TextColumn(t("材质")),
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t(item_label)),
            "总库存": st.column_config.NumberColumn(t("总库存"), format="%d"),
        },
    )


def render_sku_editor(supabase, department, inventory_df):
    st.subheader(t("修改 SKU"))
    source_df = build_sku_identity_table(inventory_df)
    if source_df.empty:
        st.info(t("暂无可修改 SKU"))
        return

    version = st.session_state.get("sku_identity_editor_version", 0)
    signature = hashlib.sha256(
        source_df["当前 SKU"].to_csv(index=False).encode("utf-8")
    ).hexdigest()[:10]
    edited_df = st.data_editor(
        source_df,
        hide_index=True,
        width="stretch",
        disabled=["当前 SKU", "尺码", "总库存"],
        column_config={
            "当前 SKU": st.column_config.TextColumn(t("当前 SKU")),
            "品类": st.column_config.TextColumn(t("品类")),
            "品牌": st.column_config.TextColumn(t("品牌")),
            "材质": st.column_config.TextColumn(t("材质"), required=True),
            "颜色": st.column_config.TextColumn(t("颜色"), required=True),
            "尺码": st.column_config.TextColumn(t(_item_label(inventory_df))),
            "总库存": st.column_config.NumberColumn(t("总库存"), format="%d"),
        },
        key=f"sku_identity_editor_{version}_{signature}",
    )
    try:
        changes = build_sku_identity_changes(
            source_df, pd.DataFrame(edited_df)
        )
    except ValueError as error:
        st.error(str(error))
        changes = []

    st.metric(t("待保存修改"), len(changes))
    confirmed = st.checkbox(
        t("我确认修改这些 SKU 资料"),
        key=f"confirm_sku_identity_changes_{version}",
    )
    if not st.button(
        t("保存 SKU 修改"), width="stretch",
        disabled=not confirmed or not changes,
    ):
        return

    try:
        updated = update_sku_identities(
            supabase, department, changes, get_current_operator_name()
        )
    except Exception as error:
        st.error(f"{t('SKU 修改失败')}: {error}")
        st.info(t("请先运行 SKU 修改 SQL"))
        return
    st.session_state["inventory_saved_message"] = t(
        "SKU 修改已保存"
    ).format(count=updated)
    st.session_state["sku_identity_editor_version"] = version + 1
    st.rerun()


def _item_label(inventory_df):
    sizes = {
        str(value).strip() for value in inventory_df.get("size", [])
        if pd.notna(value) and str(value).strip()
    }
    apparel_sizes = {"S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"}
    return "包含尺码" if not sizes or sizes.issubset(apparel_sizes) else "包含型号"
