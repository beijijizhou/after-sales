import streamlit as st

from db.daily_work import create_task, load_tasks, set_task_active
from ui.daily_work.models import TASK_KIND_LABELS
from ui.table_layout import fit_table_height


def render_task_settings(supabase, owner, actor):
    st.subheader("工作事项设置")
    st.caption("任务属于当前登录账号；停用后不会出现在新的每日记录中，历史仍会保留。")
    with st.form("daily_work_add_task"):
        section = st.text_input("工作分类", placeholder="例如：客户对接")
        task_name = st.text_input("工作事项")
        kind_label = st.selectbox("任务类型", list(TASK_KIND_LABELS.values()))
        sort_order = st.number_input("显示顺序", min_value=1, value=100, step=10)
        submitted = st.form_submit_button("添加工作事项", width="stretch")
    if submitted:
        kind = next(code for code, label in TASK_KIND_LABELS.items() if label == kind_label)
        try:
            create_task(
                supabase, owner, section, task_name, kind, sort_order, actor
            )
        except Exception as error:
            st.error(f"添加失败：{error}")
        else:
            st.success("工作事项已添加")
            st.rerun()
    try:
        tasks = load_tasks(supabase, owner, active_only=False)
    except Exception as error:
        st.error(f"任务设置加载失败：{error}")
        return
    if tasks.empty:
        return
    display = tasks[["section", "task_name", "task_kind", "sort_order", "is_active"]].copy()
    display.columns = ["分类", "工作事项", "类型", "顺序", "启用"]
    display["类型"] = display["类型"].map(TASK_KIND_LABELS)
    st.dataframe(
        display, hide_index=True, width="stretch",
        height=fit_table_height(display),
    )
    labels = {
        str(row["id"]): f"{row['section']}｜{row['task_name']}"
        for row in tasks.to_dict("records")
    }
    active_ids = [str(row["id"]) for row in tasks.to_dict("records") if row.get("is_active")]
    inactive_ids = [str(row["id"]) for row in tasks.to_dict("records") if not row.get("is_active")]
    left, right = st.columns(2)
    disable = left.multiselect(
        "停用工作事项", active_ids, format_func=labels.get,
        key="daily_work_disable_tasks",
    )
    restore = right.multiselect(
        "恢复工作事项", inactive_ids, format_func=labels.get,
        key="daily_work_restore_tasks",
    )
    if st.button("保存启用状态", width="stretch"):
        try:
            set_task_active(supabase, disable, False, actor)
            set_task_active(supabase, restore, True, actor)
        except Exception as error:
            st.error(f"保存失败：{error}")
            return
        st.success("任务启用状态已更新")
        st.rerun()
