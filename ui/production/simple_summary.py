import altair as alt
import streamlit as st


def build_person_total_table(person_platform_summary):
    columns = [
        "人员", "总生产数量", "多件订单数量", "多件占比", "时产量",
    ]
    return person_platform_summary[
        [column for column in columns if column in person_platform_summary]
    ].sort_values("总生产数量", ascending=False).reset_index(drop=True)


def render_person_total_table(person_platform_summary, title):
    st.subheader(f"{title}人员产量")
    st.dataframe(
        build_person_total_table(person_platform_summary),
        hide_index=True,
        width="stretch",
        column_config={
            "总生产数量": st.column_config.NumberColumn("总件数"),
            "多件订单数量": st.column_config.NumberColumn("多件订单数量"),
            "多件占比": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "时产量": st.column_config.NumberColumn(format="%.1f"),
        },
    )


def render_hourly_total(hourly_summary):
    if hourly_summary.empty:
        return
    st.subheader("每小时产量")
    chart_df = hourly_summary.assign(
        小时=lambda data: data["hour"].dt.strftime("%H:00")
    ).rename(columns={"scan_count": "总产量"})
    st.metric("总产量", int(chart_df["总产量"].sum()))
    chart = alt.Chart(chart_df).mark_bar(
        color="#0F766E", size=28
    ).encode(
        x=alt.X("小时:N", title="小时"),
        y=alt.Y("总产量:Q", title="产量"),
        tooltip=[
            alt.Tooltip("小时:N", title="小时"),
            alt.Tooltip("总产量:Q", title="总产量"),
        ],
    )
    st.altair_chart(chart.properties(height=360), width="stretch")
