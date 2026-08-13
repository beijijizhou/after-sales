import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    build_color_inventory_table,
    build_material_color_inventory_table,
)
from ui.inventory.i18n import t
from utils.option_values import unique_values


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
        materials = unique_values(black_white_df.get("材质", []))
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

    materials = unique_values(black_white_df.get("材质", []))
    brands = unique_values(black_white_df.get("品牌", []))
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


def render_colored_brand_merged_summary(
    inventory_df, visible_sizes=None, filter_title=None,
):
    summary_df = build_material_color_inventory_table(inventory_df)
    st.subheader(f"{filter_title or '彩色短袖'} 品牌合并库存")
    st.caption("同一材质、颜色和尺码已合并全部品牌；品牌明细仍保留用于修改和追溯。")
    if summary_df.empty:
        st.info("暂无彩色短袖库存数据")
        return
    sizes = visible_sizes or SIZE_COLUMNS
    table_height = min(max((len(summary_df) + 1) * 35 + 8, 220), 900)
    st.dataframe(
        summary_df[["材质", "颜色", *sizes, "总库存"]],
        hide_index=True,
        width="stretch",
        height=table_height,
        row_height=35,
        column_config={
            "材质": st.column_config.TextColumn(t("材质"), width="small"),
            "颜色": st.column_config.TextColumn(t("颜色"), width="small"),
            "总库存": st.column_config.NumberColumn(
                t("总库存"), format="%d", width="small"
            ),
            **{
                size: st.column_config.NumberColumn(
                    size, format="%d", width="small"
                )
                for size in SIZE_COLUMNS
            },
        },
    )
