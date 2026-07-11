import altair as alt
import streamlit as st


def render_kpis(user_summary, working_hours):
    total_count = int(user_summary["scan_count"].sum())
    multiple_order_count = int(user_summary["multiple_order_count"].sum())
    active_people = len(user_summary)
    average_df = user_summary[user_summary["scan_count"] >= 500]
    average_count = int(average_df["scan_count"].sum())
    average_people = len(average_df)
    hourly_per_person = (
        average_count / average_people / working_hours
        if average_people and working_hours
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总生产数量", total_count)
    col2.metric("多件订单数量", multiple_order_count)
    col3.metric("参与人数", active_people)
    col4.metric("人均小时产量", f"{hourly_per_person:.1f}", delta=f"按 {average_people} 人计算", delta_color="off")


def get_working_hours_from_user_summary(user_summary):
    if user_summary.empty or "working_hours" not in user_summary.columns:
        return 0

    valid_hours = (
        user_summary["working_hours"]
        .replace([float("inf"), -float("inf")], 0)
        .fillna(0)
    )
    return float(valid_hours.max()) if not valid_hours.empty else 0


def render_person_platform_table(person_platform_summary, title):
    st.subheader(f"{title}人员平台明细")
    platform_columns = [
        column
        for column in person_platform_summary.columns
        if column not in {"人员", "总生产数量", "多件订单数量", "时产量", "Haloo 数量", "Haloo 占比"}
    ]
    column_config = {
        "Haloo 占比": st.column_config.ProgressColumn("Haloo 占比", format="%.1f%%", min_value=0, max_value=100),
        "时产量": st.column_config.NumberColumn("时产量", format="%.1f"),
        "多件订单数量": st.column_config.NumberColumn("多件订单数量"),
    }
    for column in platform_columns:
        column_config[column] = st.column_config.NumberColumn(column)

    st.dataframe(person_platform_summary, hide_index=True, use_container_width=True, column_config=column_config)


def render_hourly_production(hourly_summary):
    if hourly_summary.empty:
        return

    st.subheader("每小时产量")
    chart_df = (
        hourly_summary
        .assign(小时=lambda data: data["hour"].dt.strftime("%H:00"))
        .rename(columns={"scan_count": "总产量", "haloo_count": "Haloo 产量", "haloo_percentage": "Haloo 占比"})
    )
    chart_df["Haloo 占比"] = chart_df["Haloo 占比"].round(1)
    total_count = int(chart_df["总产量"].sum())
    haloo_count = int(chart_df["Haloo 产量"].sum())
    haloo_ratio = round(haloo_count / total_count * 100, 1) if total_count else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("总产量", total_count)
    col2.metric("Haloo 产量", haloo_count)
    col3.metric("Haloo 占比", f"{haloo_ratio:.1f}%")
    render_hourly_legend()

    base = alt.Chart(chart_df).encode(
        x=alt.X("小时:N", title="小时"),
        tooltip=[
            alt.Tooltip("小时:N", title="小时"),
            alt.Tooltip("总产量:Q", title="总产量"),
            alt.Tooltip("Haloo 产量:Q", title="Haloo 产量"),
            alt.Tooltip("Haloo 占比:Q", title="Haloo 占比", format=".1f"),
        ],
    )
    total_bar = base.mark_bar(color="#B8BEC8", size=28).encode(y=alt.Y("总产量:Q", title="产量"))
    haloo_bar = base.mark_bar(color="#2563EB", size=14).encode(y=alt.Y("Haloo 产量:Q", title="产量"))
    st.altair_chart((total_bar + haloo_bar).properties(height=360), use_container_width=True)


def render_hourly_legend():
    st.markdown(
        """
        <div style="display:flex; gap:18px; align-items:center; margin:2px 0 10px 0;">
            <div style="display:flex; align-items:center; gap:7px;">
                <span style="width:18px; height:10px; background:#B8BEC8; display:inline-block;"></span>
                <span>总产量</span>
            </div>
            <div style="display:flex; align-items:center; gap:7px;">
                <span style="width:18px; height:10px; background:#2563EB; display:inline-block;"></span>
                <span>Haloo 产量</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_person_switch_table(person_switch_df):
    if person_switch_df.empty:
        return

    st.subheader("人员平台切换分析")
    st.dataframe(
        person_switch_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "切换次数": st.column_config.NumberColumn("切换次数", format="%d"),
            "切换路径": st.column_config.TextColumn("切换路径", width="large"),
        },
    )
