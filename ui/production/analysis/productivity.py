import altair as alt
import streamlit as st

from ui.production.analysis.views import add_date_labels
from utils.production.performance import build_daily_performance_index


STATUS_COLORS = {
    "高产": "#15803D",
    "正常": "#7C3AED",
    "偏低": "#DC2626",
    "进行中": "#2563EB",
}


def render_productivity_chart(daily, rows):
    performance = build_daily_performance_index(rows)
    if performance.empty:
        st.info("至少需要每人3个有效工作日，才能建立个人时产基准")
        return
    classified = daily.merge(performance, on="日期", how="inner")
    chart_df = add_date_labels(
        classified[
            classified["团队表现指数"].notna()
        ]
    )
    if chart_df.empty:
        st.info("暂无满足统计口径的人均时产数据")
        return

    high_days = int((chart_df["时产状态"] == "高产").sum())
    low_days = int((chart_df["时产状态"] == "偏低").sum())
    completed = chart_df[chart_df["时产状态"] != "进行中"]
    average_index = (
        completed["团队表现指数"].mean()
        if not completed.empty else chart_df["团队表现指数"].mean()
    )
    st.info(
        "团队表现指数判断标准\n\n"
        "先以每位质检人员自己的历史中位时产作为 100，"
        "再取当天所有人的表现指数中位数。\n\n"
        "高产：≥110　｜　正常：>90 且 <110　｜　偏低：≤90\n\n"
        "个人基准至少需要3个有效工作日，且日产量不少于500；"
        "当天标为“进行中”，订单量只用于解释原因。"
    )
    columns = st.columns(3)
    columns[0].metric(
        "平均团队表现指数",
        f"{average_index:.1f}",
    )
    columns[1].metric("高产天数", high_days)
    columns[2].metric("偏低天数", low_days)
    st.caption("灰色柱：当日订单量｜彩色点：表现状态｜紫色虚线：基准100")

    chart = build_productivity_chart(chart_df)
    st.altair_chart(chart.properties(height=370), width="stretch")
    render_productivity_table(chart_df)


def build_productivity_chart(chart_df):
    x_axis = alt.X(
        "日期标签:N", title="日期",
        sort=chart_df["日期标签"].tolist(),
        axis=alt.Axis(labelAngle=-35),
    )
    volume = alt.Chart(chart_df).mark_bar(
        color="#A7AFBA", opacity=0.5, size=24
    ).encode(
        x=x_axis,
        y=alt.Y("总产量:Q", title="当日订单量"),
        tooltip=build_tooltip(),
    )
    rate_base = alt.Chart(chart_df).encode(x=x_axis)
    index_min = min(75, float(chart_df["团队表现指数"].min()) - 5)
    index_max = max(125, float(chart_df["团队表现指数"].max()) + 5)
    rate = rate_base.mark_line(
        color="#7C3AED", strokeWidth=2
    ).encode(
        y=alt.Y(
            "团队表现指数:Q", title="团队表现指数",
            scale=alt.Scale(domain=[index_min, index_max]),
            axis=alt.Axis(orient="right", titleColor="#7C3AED"),
        ),
    )
    points = rate_base.mark_point(
        filled=True, size=130, stroke="white", strokeWidth=1
    ).encode(
        y="团队表现指数:Q",
        color=alt.Color(
            "时产状态:N",
            scale=alt.Scale(
                domain=list(STATUS_COLORS),
                range=list(STATUS_COLORS.values()),
            ),
            legend=alt.Legend(title="时产状态"),
        ),
        tooltip=build_tooltip(),
    )
    baseline = alt.Chart(chart_df).mark_rule(
        color="#7C3AED", strokeDash=[6, 4], opacity=0.65
    ).encode(y=alt.datum(100))
    productivity = alt.layer(rate, points, baseline)
    return alt.layer(volume, productivity).resolve_scale(y="independent")


def build_tooltip():
    return [
        alt.Tooltip("完整日期:N", title="日期"),
        alt.Tooltip("总产量:Q", title="当日订单量", format=","),
        alt.Tooltip("人均小时产量:Q", title="原始人均时产", format=".1f"),
        alt.Tooltip("团队表现指数:Q", format=".1f"),
        alt.Tooltip("时产状态:N"),
        alt.Tooltip("参与人数:Q", format="d"),
    ]


def render_productivity_table(chart_df):
    display = chart_df[[
        "完整日期", "总产量", "人均小时产量",
        "团队表现指数", "时产状态", "有效人数", "参与人数",
    ]].rename(columns={
        "完整日期": "日期",
        "总产量": "当日订单量",
    })
    styled = display.style.apply(highlight_productivity_row, axis=1)
    st.dataframe(
        styled, hide_index=True, width="stretch",
        column_config={
            "当日订单量": st.column_config.NumberColumn(format="%d"),
            "人均小时产量": st.column_config.NumberColumn(
                "原始人均时产", format="%.1f"
            ),
            "团队表现指数": st.column_config.NumberColumn(format="%.1f"),
            "时产状态": st.column_config.TextColumn(
                help="高产≥110；偏低≤90；当天为进行中"
            ),
            "有效人数": st.column_config.NumberColumn(format="%d"),
            "参与人数": st.column_config.NumberColumn(format="%d"),
        },
    )


def highlight_productivity_row(row):
    color = {
        "高产": "background-color: #DCFCE7; color: #166534;",
        "偏低": "background-color: #FEE2E2; color: #991B1B;",
    }.get(row.get("时产状态"), "")
    return [color] * len(row)
