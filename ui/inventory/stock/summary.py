import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS, build_color_inventory_table
from ui.inventory.i18n import t


def render_black_white_color_summary(
    category,
    inventory_df,
    visible_sizes=None,
    filter_title=None,
):
    if category not in (None, "", "黑白短袖"):
        return

    black_white_df = inventory_df
    if not category and "品类" in inventory_df.columns:
        black_white_df = inventory_df[
            inventory_df["品类"] == "黑白短袖"
        ].reset_index(drop=True)
    if black_white_df.empty:
        return

    summary_filter_title = filter_title
    if not category:
        materials = _unique_values(black_white_df, "材质")
        summary_filter_title = t("黑白短袖")
        if materials:
            summary_filter_title += f" · {'/'.join(materials)}"
    summary_title = (
        f"{summary_filter_title} {t('整体黑白库存汇总')}"
        if summary_filter_title
        else t("整体黑白库存汇总")
    )
    st.subheader(summary_title)
    summary_df = build_color_inventory_table(black_white_df)
    if summary_df.empty:
        st.info(t("暂无黑白短袖库存数据"))
        return

    materials = _unique_values(black_white_df, "材质")
    brands = _unique_values(black_white_df, "品牌")
    if materials:
        st.caption(
            t("已合并所选材质：{materials}").format(
                materials="、".join(materials)
            )
        )
    if len(brands) > 1:
        st.caption(
            t("已合并 {count} 个品牌：{brands}").format(
                count=len(brands), brands="、".join(brands)
            )
        )

    sizes = visible_sizes or SIZE_COLUMNS
    st.dataframe(
        summary_df[["颜色", *sizes, "总库存"]],
        hide_index=True,
        width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "总库存": st.column_config.NumberColumn(
                t("总库存"), format="%d"
            ),
            **{
                size: st.column_config.NumberColumn(size, format="%d")
                for size in SIZE_COLUMNS
            },
        },
    )


def _unique_values(df, column):
    return sorted({
        str(value).strip()
        for value in df.get(column, pd.Series(dtype=str)).dropna()
        if str(value).strip()
    })
