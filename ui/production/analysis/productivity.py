import altair as alt
import streamlit as st

from ui.production.analysis.views import add_date_labels
from utils.production.period_summary import classify_productivity_days


STATUS_COLORS = {
    "高产": "#15803D",
    "正常": "#7C3AED",
    "偏低": "#DC2626",
}


def render_productivity_chart(daily):
    classified = classify_productivity_days(daily)
    chart_df = add_date_labels(
        classified[classified["参与人数"] > 0]
    )
    if chart_df.empty:
        st.info("暂无满足统计口径的人均时产数据")
        return

    baseline = float(chart_df["时产均值"].iloc[0])
    high_days = int((chart_df["时产状态"] == "高产").sum())
    low_days = int((chart_df["时产状态"] == "偏低").sum())
    columns = st.columns(3)
    columns[0].metric("周期平均时产", f"{baseline:.1f}")
    columns[1].metric("高产天数", high_days)
    columns[2].metric("偏低天数", low_days)
    st.caption(
        "高产：高于周期均值 10%｜偏低：低于周期均值 10%｜"
        "灰色柱为当日订单量"
    )

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
    rate = rate_base.mark_line(
        color="#7C3AED", strokeWidth=2
    ).encode(
        y=alt.Y(
            "人均小时产量:Q", title="人均小时产量",
            scale=alt.Scale(zero=False),
            axis=alt.Axis(orient="right", titleColor="#7C3AED"),
        ),
    )
    points = rate_base.mark_point(
        filled=True, size=130, stroke="white", strokeWidth=1
    ).encode(
        y="人均小时产量:Q",
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
    average = alt.Chart(chart_df).mark_rule(
        color="#7C3AED", strokeDash=[6, 4], opacity=0.65
    ).encode(y="mean(时产均值):Q")
    productivity = alt.layer(rate, points, average)
    return alt.layer(volume, productivity).resolve_scale(y="independent")


def build_tooltip():
    return [
        alt.Tooltip("完整日期:N", title="日期"),
        alt.Tooltip("总产量:Q", title="当日订单量", format=","),
        alt.Tooltip("人均小时产量:Q", format=".1f"),
        alt.Tooltip("与均值差异:Q", title="与均值差异", format="+.1f"),
        alt.Tooltip("时产状态:N"),
        alt.Tooltip("参与人数:Q", format="d"),
    ]


def render_productivity_table(chart_df):
    display = chart_df[[
        "完整日期", "总产量", "人均小时产量",
        "与均值差异", "时产状态", "参与人数",
    ]].rename(columns={
        "完整日期": "日期",
        "总产量": "当日订单量",
    })
    styled = display.style.apply(highlight_productivity_row, axis=1)
    st.dataframe(
        styled, hide_index=True, width="stretch",
        column_config={
            "当日订单量": st.column_config.NumberColumn(format="%d"),
            "人均小时产量": st.column_config.NumberColumn(format="%.1f"),
            "与均值差异": st.column_config.NumberColumn(format="%+.1f%%"),
            "参与人数": st.column_config.NumberColumn(format="%d"),
        },
    )


def highlight_productivity_row(row):
    color = {
        "高产": "background-color: #DCFCE7; color: #166534;",
        "偏低": "background-color: #FEE2E2; color: #991B1B;",
    }.get(row.get("时产状态"), "")
    return [color] * len(row)
