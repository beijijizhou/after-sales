from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t
from ui.inventory.stock.table_editor import render_inventory_table_editor
from ui.inventory.stock.table_filters import render_inventory_table_filters


def render_inventory_table(
    supabase, department, category, inventory_df, inventory_date, editable,
    visible_sizes, filter_title,
):
    st.subheader(f"{filter_title} {t('库存明细')}")
    current_date = datetime.now(ZoneInfo("America/New_York")).date()

    col1, col2 = st.columns(2)
    col1.metric(t("当前日期"), current_date.isoformat())
    col2.metric(t("库存日期"), inventory_date.isoformat())
    display_df = render_inventory_table_filters(inventory_df, visible_sizes)
    column_config = {
        "总库存": st.column_config.NumberColumn(
            t("总库存（全部尺码）"), format="%d"
        ),
        "品类": st.column_config.TextColumn(t("品类")),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质")),
        "颜色": st.column_config.TextColumn(t("颜色")),
        **{
            size: st.column_config.NumberColumn(size, format="%d")
            for size in SIZE_COLUMNS
        },
    }
    table_height = min(max((len(display_df) + 1) * 35 + 8, 220), 900)
    if editable:
        render_inventory_table_editor(
            supabase, department, category, display_df, column_config,
            table_height,
        )
    else:
        st.dataframe(
            display_df, hide_index=True, width="stretch",
            column_config=column_config, height=table_height,
        )


def render_inventory_metrics(inventory_df):
    table_total = int(inventory_df["总库存"].sum())
    color_count = (
        inventory_df["颜色"].nunique() if "颜色" in inventory_df.columns else 0
    )
    col1, col2 = st.columns(2)
    col1.metric(t("当前表总库存"), table_total)
    col2.metric(t("当前表颜色数"), color_count)
