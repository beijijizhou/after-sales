import altair as alt
import streamlit as st

from utils.production_helpers import (
    build_person_platform_summary,
    get_working_hours,
    load_daily_production_rows,
    prepare_production_df,
    summarize_by_client,
    summarize_by_hour,
    summarize_by_user,
)


def render_kpis(user_summary, working_hours):
    total_count = int(user_summary["scan_count"].sum())
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
    col2.metric("参与人数", active_people)
    col3.metric("工作小时", f"{working_hours:.1f}")
    col4.metric(
        "人均小时产量",
        f"{hourly_per_person:.1f}",
        delta=f"按 {average_people} 人计算",
        delta_color="off"
    )


def render_client_kpis(client_summary):
    if client_summary.empty:
        return

    client_cols = st.columns(max(len(client_summary), 1))
    for index, row in client_summary.iterrows():
        client_cols[index].metric(
            row["client"],
            int(row["scan_count"])
        )


def render_person_platform_table(person_platform_summary, title):
    st.subheader(f"{title}人员平台明细")

    platform_columns = [
        column
        for column in person_platform_summary.columns
        if column not in {"人员", "总生产数量", "Haloo 数量", "Haloo 占比"}
    ]
    column_config = {
        "Haloo 占比": st.column_config.ProgressColumn(
            "Haloo 占比",
            format="%.1f%%",
            min_value=0,
            max_value=100,
        )
    }
    for column in platform_columns:
        column_config[column] = st.column_config.NumberColumn(column)

    st.dataframe(
        person_platform_summary,
        hide_index=True,
        use_container_width=True,
        column_config=column_config
    )


def render_hourly_production(hourly_summary):
    if hourly_summary.empty:
        return

    st.subheader("每小时产量")

    chart_df = (
        hourly_summary
        .assign(小时=lambda data: data["hour"].dt.strftime("%H:00"))
        .rename(columns={
            "scan_count": "总产量",
            "haloo_count": "Haloo 产量",
            "haloo_percentage": "Haloo 占比",
        })
    )
    chart_df["Haloo 占比"] = chart_df["Haloo 占比"].round(1)
    total_count = int(chart_df["总产量"].sum())
    haloo_count = int(chart_df["Haloo 产量"].sum())
    haloo_ratio = round(haloo_count / total_count * 100, 1) if total_count else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("总产量", total_count)
    col2.metric("Haloo 产量", haloo_count)
    col3.metric("Haloo 占比", f"{haloo_ratio:.1f}%")

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
        unsafe_allow_html=True
    )

    base = alt.Chart(chart_df).encode(
        x=alt.X("小时:N", title="小时"),
        tooltip=[
            alt.Tooltip("小时:N", title="小时"),
            alt.Tooltip("总产量:Q", title="总产量"),
            alt.Tooltip("Haloo 产量:Q", title="Haloo 产量"),
            alt.Tooltip("Haloo 占比:Q", title="Haloo 占比", format=".1f"),
        ],
    )
    total_bar = base.mark_bar(color="#B8BEC8", size=28).encode(
        y=alt.Y("总产量:Q", title="产量")
    )
    haloo_bar = base.mark_bar(color="#2563EB", size=14).encode(
        y=alt.Y("Haloo 产量:Q", title="产量")
    )
    st.altair_chart((total_bar + haloo_bar).properties(height=360), use_container_width=True)


def render_production_summary(supabase, selected_date, title, user_column):
    st.title(title)

    try:
        raw_df = load_daily_production_rows(supabase, selected_date, user_column)
        if raw_df.empty:
            st.warning(f"{selected_date.isoformat()} 没有生产数据")
            st.stop()

        df = prepare_production_df(raw_df, user_column)
        if df.empty:
            st.warning(f"{selected_date.isoformat()} 没有{title}人员数据")
            st.stop()

        user_summary = summarize_by_user(df, user_column)
        client_summary = summarize_by_client(df)
        person_platform_summary = build_person_platform_summary(df, user_column)
        hourly_summary = summarize_by_hour(df, selected_date)
        working_hours = get_working_hours(df)

        render_kpis(user_summary, working_hours)
        render_client_kpis(client_summary)
        render_person_platform_table(person_platform_summary, title)
        render_hourly_production(hourly_summary)

    except Exception as e:
        st.error(f"数据加载失败：{e}")
