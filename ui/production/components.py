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

    st.dataframe(person_platform_summary, hide_index=True, width="stretch", column_config=column_config)


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
    st.altair_chart((total_bar + haloo_bar).properties(height=360), width="stretch")


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
        st.info("暂无人员平台切换数据")
        return

    st.dataframe(
        person_switch_df,
        hide_index=True,
        width="stretch",
        column_config={
            "切换次数": st.column_config.NumberColumn("切换次数", format="%d"),
            "切换路径": st.column_config.TextColumn("切换路径", width="large"),
        },
    )


def render_pair_workflow_table(workflow_df, selection_key):
    if workflow_df.empty:
        st.info("暂无质检—烫印配对工作流数据")
        return

    st.caption(
        "每个质检人员一行；只有对应的烫印人员变化时，才进入下一段配对工作。"
    )
    summary_df = workflow_df.drop(columns=["工作流"])
    st.dataframe(
        summary_df,
        hide_index=True,
        width="stretch",
        column_config={
            "质检人员": st.column_config.TextColumn("质检人员"),
            "主要烫印人员": st.column_config.TextColumn("主要烫印人员"),
            "烫印人员明细": st.column_config.TextColumn(
                "烫印人员明细", width="large"
            ),
            "总产量": st.column_config.NumberColumn("总产量", format="%d"),
            "切换次数": st.column_config.NumberColumn("切换次数", format="%d"),
        },
    )
    people_options = sorted(workflow_df["质检人员"].tolist())
    if (
        selection_key in st.session_state
        and st.session_state[selection_key] not in people_options
    ):
        del st.session_state[selection_key]
    selected_person = st.selectbox(
        "查看质检人员完整配对工作流",
        people_options,
        key=selection_key,
    )
    selected_row = workflow_df.loc[
        workflow_df["质检人员"] == selected_person
    ].iloc[0]
    selected_name = selected_row["质检人员"]
    selected_workflow = selected_row["工作流"]
    st.markdown(f"**{selected_name} 配对工作流**")
    st.markdown("\n".join(
        f"- {step}" for step in selected_workflow.split(" → ")
    ))


def render_workflow_analysis(
    person_switch_df, pair_workflow_df, title, selected_date
):
    st.subheader("工作流分析")
    platform_tab, pair_tab = st.tabs([
        f"{title}人员平台分析",
        "质检—烫印配对",
    ])
    with platform_tab:
        render_person_switch_table(person_switch_df)
    with pair_tab:
        render_pair_workflow_table(
            pair_workflow_df,
            selection_key=(
                f"pair_workflow_person_v2_{title}_"
                f"{selected_date.isoformat()}"
            ),
        )
