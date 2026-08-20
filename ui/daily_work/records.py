from datetime import timedelta

import pandas as pd
import streamlit as st

from db.daily_work import (
    load_daily_work,
    load_daily_work_history,
    load_tasks,
    save_daily_work,
)
from ui.daily_work.models import (
    STATUS_LABELS,
    build_daily_editor,
    completion_summary,
    editor_records,
    history_detail,
    history_summary,
    style_status_table,
)
from ui.table_layout import fit_table_height


def render_daily_record(supabase, owner, actor, today):
    selected_date = st.date_input(
        "工作日期", value=today, key="daily_work_date"
    )
    try:
        tasks = load_tasks(supabase, owner)
        day, records = load_daily_work(supabase, owner, selected_date)
    except Exception as error:
        st.error(f"每日工作加载失败：{error}")
        return
    if tasks.empty:
        st.info("当前还没有工作事项，请先到“任务设置”添加。")
        return
    editor = build_daily_editor(tasks, records)
    edited = st.data_editor(
        editor,
        hide_index=True,
        width="stretch",
        disabled=["_task_id", "_task_kind", "类别", "类型", "工作事项"],
        column_config={
            "_task_id": None,
            "_task_kind": None,
            "类别": st.column_config.TextColumn("类别", width="small"),
            "类型": st.column_config.TextColumn("类型", width="small"),
            "工作事项": st.column_config.TextColumn("工作事项", width="large"),
            "状态": st.column_config.SelectboxColumn(
                "状态", options=list(STATUS_LABELS.values()), required=True,
                width="small",
            ),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
        height=fit_table_height(editor, row_height=42),
        row_height=42,
        key=f"daily_work_editor_{owner}_{selected_date.isoformat()}",
    )
    _render_metrics(completion_summary(pd.DataFrame(edited)))
    summary = st.text_area(
        "当日总结", value=str(day.get("summary") or ""),
        key=f"daily_work_summary_{selected_date}",
    )
    blockers, next_plan = st.columns(2)
    blocker_text = blockers.text_area(
        "问题 / 阻塞", value=str(day.get("blockers") or ""),
        key=f"daily_work_blockers_{selected_date}",
    )
    next_text = next_plan.text_area(
        "明日计划", value=str(day.get("next_plan") or ""),
        key=f"daily_work_next_{selected_date}",
    )
    if st.button("保存当天记录", type="primary", width="stretch"):
        try:
            save_daily_work(
                supabase, owner, selected_date, summary, blocker_text,
                next_text, editor_records(pd.DataFrame(edited)), actor,
            )
        except Exception as error:
            st.error(f"保存失败：{error}")
            return
        st.session_state["daily_work_saved_message"] = (
            f"{selected_date:%Y-%m-%d} 的工作记录已保存"
        )
        st.rerun()


def render_history(supabase, owner, today):
    start_date, end_date = st.date_input(
        "查看日期范围",
        value=(today - timedelta(days=13), today),
        key="daily_work_history_range",
    )
    try:
        days, records = load_daily_work_history(
            supabase, owner, start_date, end_date
        )
    except Exception as error:
        st.error(f"历史记录加载失败：{error}")
        return
    summary = history_summary(days, records)
    if summary.empty:
        st.info("所选日期范围内还没有保存记录。")
        return
    st.dataframe(
        summary, hide_index=True, width="stretch",
        height=fit_table_height(summary),
        column_config={"完成率": st.column_config.ProgressColumn("完成率", min_value=0, max_value=100, format="%d%%")},
    )
    labels = {
        str(row["id"]): str(row["work_date"])
        for row in days.to_dict("records")
    }
    selected = st.selectbox(
        "查看某天明细", list(labels), format_func=labels.get,
        key="daily_work_history_day",
    )
    detail = history_detail(selected, records)
    st.dataframe(
        style_status_table(detail), hide_index=True, width="stretch",
        height=fit_table_height(detail),
    )
    day = next(row for row in days.to_dict("records") if str(row["id"]) == selected)
    st.caption(f"问题 / 阻塞：{day.get('blockers') or '无'}")
    st.caption(f"明日计划：{day.get('next_plan') or '无'}")


def _render_metrics(summary):
    columns = st.columns(4)
    columns[0].metric("完成率", f"{summary['rate']}%")
    columns[1].success(f"🟢 已完成\n\n{summary['completed']} 项")
    columns[2].warning(f"🟡 待处理\n\n{summary['pending']} 项")
    columns[3].info(f"⚪ 不适用\n\n{summary['not_applicable']} 项")
