import streamlit as st
import altair as alt
import pandas as pd

from db.inventory import (
    SIZE_COLUMNS,
    build_color_inventory_table,
    build_material_color_inventory_table,
)
from ui.inventory.i18n import t
from utils.option_values import unique_values
from db.inventory.planning.demand_anomaly import load_daily_outbound_history
from db.inventory.planning.warehouse_usage import build_stock_outbound_ratio_series


def render_black_white_color_summary(
    category,
    inventory_df,
    visible_sizes=None,
    filter_title=None,
    *, supabase=None, current_date=None, stock_date=None,
    brands=None, materials=None,
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
    summary_level = st.segmented_control(
        t("汇总层级"),
        ["整体合计", "按材质分层"],
        default="整体合计",
        format_func=t,
        key="black_white_inventory_summary_level",
    )
    if summary_level == "按材质分层":
        summary_df = build_material_color_inventory_table(black_white_df)
    else:
        summary_df = build_color_inventory_table(black_white_df)
    if summary_df.empty:
        st.info(t("暂无黑白短袖库存数据"))
        return

    materials = unique_values(black_white_df.get("材质", []))
    brands = unique_values(black_white_df.get("品牌", []))
    if materials and summary_level == "整体合计":
        st.caption(
            t("已合并所选材质：{materials}").format(
                materials="、".join(materials)
            )
        )
    elif materials:
        st.caption(t("每个材质分别汇总，材质内合并所选品牌。"))
    if len(brands) > 1:
        st.caption(
            t("已合并 {count} 个品牌：{brands}").format(
                count=len(brands), brands="、".join(brands)
            )
        )

    sizes = visible_sizes or SIZE_COLUMNS
    leading_columns = ["材质", "颜色"] if summary_level == "按材质分层" else ["颜色"]
    table_height = min(max((len(summary_df) + 1) * 35 + 8, 150), 900)
    st.dataframe(
        summary_df[[*leading_columns, *sizes, "总库存"]],
        hide_index=True,
        width="stretch",
        height=table_height,
        row_height=35,
        column_config={
            "材质": st.column_config.TextColumn(t("材质"), width="small"),
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
    if supabase is not None and current_date is not None:
        render_black_white_ratio_comparison(
            supabase, black_white_df, current_date, sizes, stock_date,
            brands=brands, materials=materials,
        )


def render_black_white_ratio_comparison(
    supabase, inventory_df, current_date, sizes, stock_date=None,
    *, brands=None, materials=None,
):
    st.markdown("#### 颜色尺码结构：当前库存 vs 最近30天出库")
    if not {"黑", "白"}.issubset(set(inventory_df["颜色"])):
        st.info("请同时选择黑色和白色，才能比较整体黑白库存与出库比例。")
        return
    try:
        with st.spinner("正在读取最近30天人工出库…"):
            outbound = load_daily_outbound_history(
                supabase, "DTF", "黑白短袖", current_date,
                lookback_days=31,
                brands=brands, materials=materials,
            )
            data = build_stock_outbound_ratio_series(
                inventory_df, outbound, current_date, sizes=SIZE_COLUMNS,
            )
    except Exception as exc:
        st.error("库存与出库比例加载失败，请重试。")
        st.caption(str(exc))
        return
    metrics = st.columns(2)
    for column, series in zip(metrics, ("当前库存比例", "最近30天出库比例")):
        total = data[data["曲线"].eq(series)]["总量"].iloc[0]
        column.metric(
            "当前黑白总库存" if series == "当前库存比例" else "最近30天黑白总出库",
            f"{total:,} 件",
        )
    st.caption(
        f"库存快照：{stock_date or current_date}；出库范围："
        f"{data['开始日期'].iloc[0]:%m/%d}–{data['结束日期'].iloc[0]:%m/%d}（不含今天）。"
        "每个点是该颜色＋尺码占全部黑白短袖的百分比，每条曲线合计100%。"
        "沿用品牌、材质筛选，展示全部尺码。"
    )
    recorded = int(data["登记天数"].iloc[0])
    st.caption(
        f"有出库登记 {recorded}/30 天。库存线高于出库线表示该颜色尺码库存相对偏多，"
        "低于则相对偏少；这是结构对比，不代表绝对库存充足。"
    )
    order = [f"{color}{size}" for color in ("黑", "白") for size in SIZE_COLUMNS]
    chart = alt.Chart(data).mark_line(point=True).encode(
            x=alt.X("颜色尺码:N", title="颜色＋尺码", sort=order, axis=alt.Axis(labelAngle=-35)),
            y=alt.Y("占比:Q", title="占全部黑白短袖的比例", scale=alt.Scale(zero=True), axis=alt.Axis(format=".0%")),
            color=alt.Color("曲线:N", title=None, sort=["当前库存比例", "最近30天出库比例"]),
            strokeDash=alt.StrokeDash("曲线:N", legend=None),
            tooltip=["颜色尺码:N", "曲线:N",
                     alt.Tooltip("占比:Q", format=".1%"), "数量:Q", "总量:Q"],
        ).properties(height=320)
    stock_labels = alt.Chart(data[data["曲线"].eq("当前库存比例")]).mark_text(dy=-12).encode(
        x=alt.X("颜色尺码:N", sort=order), y="占比:Q", text=alt.Text("占比:Q", format=".1%"),
    )
    usage_labels = alt.Chart(data[data["曲线"].eq("最近30天出库比例")]).mark_text(dy=14).encode(
        x=alt.X("颜色尺码:N", sort=order), y="占比:Q", text=alt.Text("占比:Q", format=".1%"),
    )
    st.altair_chart(chart + stock_labels + usage_labels, width="stretch")
    if not recorded:
        st.info("最近30天暂无有效人工出库，暂时无法判断库存结构是否合理。")


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
