import altair as alt
import streamlit as st

from ui.production.components import render_person_platform_table
from ui.production.daily_workflow import render_daily_workflow
from ui.production.period_filters import render_period_filters
from utils.production import load_period_person_platform_rows
from utils.production.period_summary import (
    build_daily_summary,
    build_period_person_platform_summary,
    build_platform_summary,
    get_period_dates,
    prepare_period_rows,
)


def render_qa_period_analysis(
    supabase, selected_date, user_column, snapshot_at=None
):
    start_date, end_date = get_period_dates(selected_date)
    st.subheader("质检生产汇总")
    st.caption(
        f"默认分析最近14天：{start_date.isoformat()} 至 "
        f"{end_date.isoformat()}（纽约时间）"
    )

    try:
        rpc_rows = load_period_person_platform_rows(
            supabase, start_date, end_date, user_column, snapshot_at
        )
    except Exception as error:
        st.warning("14天汇总函数尚未更新")
        st.caption(
            "请在 Supabase SQL Editor 运行 "
            "sql/qa_period_summary_functions.sql"
        )
        st.caption(str(error))
        return

    rows = prepare_period_rows(rpc_rows)
    if rows.empty:
        st.info("所选日期之前14天没有质检数据")
        return

    filtered, filter_state = render_period_filters(
        rows, start_date, end_date
    )
    if filtered.empty:
        st.info("当前筛选条件没有质检数据")
        return

    daily = build_daily_summary(
        filtered, filter_state.start_date, filter_state.end_date
    )
    render_summary_metrics(filtered, daily)
    people_tab, daily_tab, platform_tab, rate_tab, workflow_tab = st.tabs([
        "人员平台明细", "每日汇总", "平台构成",
        "人均时产", "单日工作流",
    ])
    with people_tab:
        render_person_platform_table(
            build_period_person_platform_summary(filtered), "质检"
        )
    with daily_tab:
        render_daily_summary(daily)
    with platform_tab:
        render_platform_summary(build_platform_summary(filtered))
    with rate_tab:
        render_productivity_chart(daily)
    with workflow_tab:
        render_daily_workflow(
            supabase, filter_state, user_column, snapshot_at
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
    chart_data = daily.melt(
        id_vars=["日期"],
        value_vars=["总产量", "多件数量"],
        var_name="指标",
        value_name="数量",
    )
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("日期:T", title="日期", axis=alt.Axis(format="%m/%d")),
        y=alt.Y("数量:Q", title="数量"),
        color=alt.Color(
            "指标:N", scale=alt.Scale(
                domain=["总产量", "多件数量"],
                range=["#B8BEC8", "#2563EB"],
            )
        ),
        xOffset="指标:N",
        tooltip=[
            alt.Tooltip("日期:T", title="日期", format="%Y-%m-%d"),
            alt.Tooltip("指标:N"),
            alt.Tooltip("数量:Q", format=","),
        ],
    )
    st.altair_chart(chart.properties(height=330), width="stretch")
    display = daily.copy()
    display["日期"] = display["日期"].dt.strftime("%Y-%m-%d")
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


def render_productivity_chart(daily):
    chart_df = daily[daily["参与人数"] > 0].copy()
    if chart_df.empty:
        st.info("暂无满足统计口径的人均时产数据")
        return
    st.caption("统计口径：仅计算当日产量不少于 500 的质检人员")
    chart = alt.Chart(chart_df).mark_line(
        color="#7C3AED", point=True, strokeWidth=3
    ).encode(
        x=alt.X("日期:T", title="日期", axis=alt.Axis(format="%m/%d")),
        y=alt.Y("人均小时产量:Q", title="人均小时产量", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("日期:T", format="%Y-%m-%d"),
            alt.Tooltip("人均小时产量:Q", format=".1f"),
            alt.Tooltip("参与人数:Q", format="d"),
        ],
    )
    st.altair_chart(chart.properties(height=350), width="stretch")
