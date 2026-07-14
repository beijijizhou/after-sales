import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t


def render_inventory_table_filters(inventory_df, category):
    if inventory_df.empty:
        return inventory_df

    filter_col, size_col = st.columns(2)
    color_values = inventory_df["颜色"] if "颜色" in inventory_df.columns else []
    colors = list(dict.fromkeys(
        str(value) for value in color_values if str(value).strip()
    ))
    selected_color = filter_col.selectbox(
        t("筛选颜色"),
        ["全部", *colors],
        format_func=t,
        key=f"inventory_color_filter_{category}",
    )
    selected_sizes = size_col.multiselect(
        t("显示尺码"),
        SIZE_COLUMNS,
        default=SIZE_COLUMNS,
        key=f"inventory_size_filter_{category}",
    )

    display_df = inventory_df.copy()
    if selected_color != "全部":
        display_df = display_df[display_df["颜色"] == selected_color]

    fixed_columns = [
        column
        for column in ["品类", "品牌", "材质", "颜色", "成本"]
        if column in display_df.columns
    ]
    total_columns = ["总库存"] if "总库存" in display_df.columns else []
    return display_df[[*fixed_columns, *selected_sizes, *total_columns]]
