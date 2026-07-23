import altair as alt
import streamlit as st

from utils.date_display import (
    format_chart_date,
    format_date_with_weekday,
)


def render_summary_metrics(rows, daily):
    total = int(daily["总产量"].sum())
    multiple = int(daily["多件数量"].sum())
    ratio = multiple / total * 100 if total else 0
    rates = daily.loc[daily["参与人数"] > 0, "人均小时产量"]
    average_rate = rates.mean() if not rates.empty else 0
    columns = st.columns(4)
    columns[0].metric("总生产数量", f"{total:,}")
    columns[1].metric(
        "多件订单数量", f"{multiple:,}",
        delta=f"占比 {ratio:.1f}%", delta_color="off",
    )
    columns[2].metric("参与人数", rows["人员"].nunique())
    columns[3].metric(
        "人均小时产量", f"{average_rate:.1f}",
        delta="按每日产量不少于 500 人员计算",
        delta_color="off",
    )


def render_daily_summary(daily):
    dated = add_date_labels(daily)
    chart_data = dated.melt(
        id_vars=["日期", "日期标签", "完整日期"],
        value_vars=["总产量", "多件数量"],
        var_name="指标",
        value_name="数量",
    )
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X(
            "日期标签:N", title="日期",
            sort=dated["日期标签"].tolist(),
            axis=alt.Axis(labelAngle=-35),
        ),
        y=alt.Y("数量:Q", title="数量"),
        color=alt.Color(
            "指标:N", scale=alt.Scale(
                domain=["总产量", "多件数量"],
                range=["#B8BEC8", "#2563EB"],
            )
        ),
        xOffset="指标:N",
        tooltip=[
            alt.Tooltip("完整日期:N", title="日期"),
            alt.Tooltip("指标:N"),
            alt.Tooltip("数量:Q", format=","),
        ],
    )
    st.altair_chart(chart.properties(height=330), width="stretch")
    display = daily.copy()
    display["日期"] = display["日期"].apply(format_date_with_weekday)
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_config={
            "多件占比": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "人均小时产量": st.column_config.NumberColumn(format="%.1f"),
        },
    )


def render_platform_summary(summary):
    if summary.empty:
        st.info("暂无平台数据")
        return
    chart = alt.Chart(summary).mark_bar(color="#0F766E").encode(
        x=alt.X("产量:Q", title="筛选产量"),
        y=alt.Y("平台:N", title=None, sort="-x"),
        tooltip=[
            alt.Tooltip("平台:N"),
            alt.Tooltip("产量:Q", format=","),
            alt.Tooltip("占比:Q", format=".1f"),
        ],
    )
    st.altair_chart(chart.properties(height=360), width="stretch")
    st.dataframe(
        summary, hide_index=True, width="stretch",
        column_config={
            "产量": st.column_config.NumberColumn(format="%d"),
            "占比": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
        },
    )


def render_client_summary(daily):
    haloo_total = int(daily["Haloo"].sum())
    other_total = int(daily["小平台"].sum())
    total = haloo_total + other_total
    columns = st.columns(3)
    columns[0].metric("Haloo", f"{haloo_total:,}")
    columns[1].metric("小平台", f"{other_total:,}")
    columns[2].metric(
        "Haloo 占比",
        f"{haloo_total / total * 100 if total else 0:.1f}%",
    )
    dated = add_date_labels(daily)
    chart_data = dated.melt(
        id_vars=["日期", "日期标签", "完整日期"],
        value_vars=["Haloo", "小平台"],
        var_name="客户类型",
        value_name="产量",
    )
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X(
            "日期标签:N", title="日期",
            sort=dated["日期标签"].tolist(),
            axis=alt.Axis(labelAngle=-35),
        ),
        y=alt.Y("产量:Q", title="产量"),
        xOffset="客户类型:N",
        color=alt.Color(
            "客户类型:N",
            scale=alt.Scale(
                domain=["Haloo", "小平台"],
                range=["#2563EB", "#D97706"],
            ),
        ),
        tooltip=[
            alt.Tooltip("完整日期:N", title="日期"),
            alt.Tooltip("客户类型:N"),
            alt.Tooltip("产量:Q", format=","),
        ],
    )
    st.altair_chart(chart.properties(height=340), width="stretch")


def add_date_labels(df):
    result = df.copy()
    result["日期标签"] = result["日期"].apply(format_chart_date)
    result["完整日期"] = result["日期"].apply(
        format_date_with_weekday
    )
    return result
