import streamlit as st

from db.inventory.planning.consumption_comparison import build_period_model_comparison
from ui.inventory.i18n import t


def render_model_comparison(model_df, outbound_df, current_date):
    days = st.selectbox(
        t("统计周期"),
        [3, 7, 14, 28],
        index=2,
        format_func=lambda value: f"{value} {t('天')}",
        key="inventory_consumption_comparison_days",
    )
    comparison_df = build_period_model_comparison(
        model_df, outbound_df, current_date, days
    )
    st.subheader(t("近{days}日出库与模型对比").format(days=days))
    st.caption(t("所有品牌和材质按黑白颜色及尺码合并，有效天数按已录入每日出库计算。"))
    if comparison_df.empty:
        st.info(t("暂无周期对比数据"))
        return

    display_df = comparison_df.copy()
    display_df["颜色"] = display_df["颜色"].map(t)
    styled_df = display_df.style.apply(highlight_gap, axis=1)
    st.dataframe(
        styled_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t("尺码")),
            "模型日耗": st.column_config.NumberColumn(t("模型日耗"), format="%d"),
            "期间实际日均": st.column_config.NumberColumn(
                t("期间实际日均"), format="%d"
            ),
            "日均差额": st.column_config.NumberColumn(t("日均差额"), format="%d"),
            "差距%": st.column_config.NumberColumn(t("差距%"), format="%.1f%%"),
            "有效出库天数": st.column_config.NumberColumn(
                t("有效出库天数"), format="%d"
            ),
        },
    )


def highlight_gap(row):
    gap = row.get("差距%")
    try:
        gap = float(gap)
    except (TypeError, ValueError):
        gap = 0
    if gap >= 30:
        style = "background-color: #ffd6d6; color: #8a0000; font-weight: 700;"
    elif gap >= 15:
        style = "background-color: #fff1cc; color: #7a4a00; font-weight: 700;"
    else:
        style = ""
    return [style if column in ["期间实际日均", "日均差额", "差距%"] else "" for column in row.index]
