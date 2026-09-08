"""SKU-import history tables."""

import pandas as pd
import streamlit as st

from ui.inventory.history.core.tables import (
    _display_item_columns,
    format_date_columns,
)
from ui.inventory.i18n import t
from utils.auth import has_permission


def build_sku_import_detail_table(sku_import_df, visible_sizes=None):
    if sku_import_df.empty:
        return pd.DataFrame()

    import_df = format_date_columns(sku_import_df, ["import_date"])
    include_cost = has_permission("can_view_cost")
    index_columns = [
        "import_date", "department", "category", "brand", "material", "color",
    ]
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
    sizes = _display_item_columns(import_df, visible_sizes)
    for size in sizes:
        if size not in display_df.columns:
            display_df[size] = 0
    cost_columns = ["成本"] if include_cost else []
    optional_columns = [
        column for column in ["部门", "品类"] if column in display_df.columns
    ]
    display_df = display_df[[
        "日期", *optional_columns, "品牌", "材质", "颜色", *cost_columns,
        *sizes,
    ]]
    column_config = {
        "日期": st.column_config.DateColumn(t("日期")),
        "部门": st.column_config.TextColumn(t("部门")),
        "品类": st.column_config.TextColumn(t("品类")),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质")),
        "颜色": st.column_config.TextColumn(t("颜色")),
        **{size: st.column_config.NumberColumn(size) for size in sizes},
    }
    if "成本" in display_df.columns:
        column_config["成本"] = st.column_config.NumberColumn(
            t("成本"), format="%.4f"
        )
    return display_df, column_config


def render_sku_import_table(sku_import_df, visible_sizes=None):
    st.subheader(t("SKU 导入明细"))
    table_result = build_sku_import_detail_table(sku_import_df, visible_sizes)
    if isinstance(table_result, pd.DataFrame) and table_result.empty:
        st.info(t("暂无 SKU 导入明细"))
        return
    display_df, column_config = table_result
    st.dataframe(
        display_df, hide_index=True, width="stretch",
        column_config=column_config,
    )
