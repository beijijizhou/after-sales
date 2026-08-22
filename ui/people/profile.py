import pandas as pd
import streamlit as st

from db.access import (
    load_employee_profile_audit,
    load_production_departments,
    update_employee_profile,
)
from ui.people.models import employee_label, reset_stale_employee_selection
from utils.auth import get_current_user


JOB_TITLES = ("质检", "烫印")


def render_employee_profile_editor(supabase, employees):
    records = {
        str(row["employee_id"]): row for row in employees.to_dict("records")
    }
    reset_stale_employee_selection(
        st.session_state, "people_profile_employee", records
    )
    selected_id = st.selectbox(
        "选择员工", list(records),
        format_func=lambda value: employee_label(records[value]),
        key="people_profile_employee",
    )
    selected = records[selected_id]
    current_title = str(selected.get("job_title") or "员工")
    title_options = list(dict.fromkeys([*JOB_TITLES, current_title]))
    department_options = load_production_departments(supabase)
    current_departments = list(selected.get("departments") or ["DTF"])

    new_title = st.selectbox(
        "岗位", title_options, index=title_options.index(current_title),
        key=f"people_profile_job_title_{selected_id}",
    )
    new_departments = st.multiselect(
        "生产部门（可多选）", department_options,
        default=[
            value for value in current_departments
            if value in department_options
        ],
        key=f"people_profile_departments_{selected_id}",
    )
    preview = employee_profile_preview(
        selected, new_title, new_departments
    )
    st.caption("资料变更预览")
    st.dataframe(pd.DataFrame([preview]), hide_index=True, width="stretch")
    confirmed = st.checkbox(
        "我已核对岗位和生产部门变化",
        key=f"people_profile_confirmed_{selected_id}",
    )
    submitted = st.button(
        "保存员工资料", type="primary",
        disabled=not confirmed or not preview["是否变化"],
        key=f"people_profile_submit_{selected_id}",
    )
    if not submitted:
        return
    actor = str((get_current_user() or {}).get("username") or "").strip()
    try:
        update_employee_profile(
            supabase, selected_id, new_title, new_departments, actor,
        )
    except Exception as error:
        if "update_employee_profile" in str(error):
            st.error(
                "员工资料调整尚未初始化，请执行 "
                "sql/access/role_management/14_employee_profile_management.sql。"
            )
        else:
            st.error(str(error))
        return
    st.session_state["people_management_notice"] = (
        f"已更新 {selected['name']}：岗位 {new_title}，"
        f"生产部门 {' / '.join(new_departments)}。"
    )
    st.rerun()


def render_employee_profile_history(supabase):
    try:
        rows = load_employee_profile_audit(supabase)
    except Exception as error:
        if "app_employee_profile_audit" in str(error):
            st.info("执行员工资料调整数据库脚本后，这里会显示变更记录。")
        else:
            st.error("员工资料变更记录暂时无法读取，请稍后重试。")
        return
    if rows.empty:
        st.info("暂无岗位或生产部门变更记录。")
        return
    display = rows.rename(columns={
        "employee_name": "员工", "old_job_title": "原岗位",
        "new_job_title": "新岗位", "old_departments": "原生产部门",
        "new_departments": "新生产部门", "changed_by": "操作人",
        "changed_at": "操作时间",
    }).copy()
    for column in ("原生产部门", "新生产部门"):
        display[column] = display[column].map(
            lambda values: " / ".join(values or [])
        )
    st.dataframe(display[[
        "员工", "原岗位", "新岗位", "原生产部门", "新生产部门",
        "操作人", "操作时间",
    ]], hide_index=True, width="stretch")


def employee_profile_preview(employee, new_title, new_departments):
    old_departments = list(employee.get("departments") or ["DTF"])
    return {
        "员工": employee_label(employee),
        "原岗位": str(employee.get("job_title") or "员工"),
        "新岗位": str(new_title),
        "原生产部门": " / ".join(old_departments),
        "新生产部门": " / ".join(new_departments),
        "是否变化": (
            str(employee.get("job_title") or "员工") != str(new_title)
            or set(old_departments) != set(new_departments)
        ),
    }
