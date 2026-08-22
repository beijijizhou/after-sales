import streamlit as st

from ui.people.models import (
    ALL_DEPARTMENTS,
    ALL_JOB_TITLES,
    employee_department_options,
    employee_job_title_options,
    employee_label,
    filter_employees_by_organization,
    reset_stale_employee_selection,
    reset_stale_filter_selection,
)


def render_employee_selector(employees, key_prefix):
    department_key = f"{key_prefix}_department"
    job_title_key = f"{key_prefix}_job_title"
    employee_key = f"{key_prefix}_employee"

    department_options = employee_department_options(employees)
    reset_stale_filter_selection(
        st.session_state, department_key, department_options
    )
    filter_columns = st.columns(2)
    department = filter_columns[0].selectbox(
        "部门", department_options, key=department_key
    )

    department_employees = filter_employees_by_organization(
        employees, department=department
    )
    job_title_options = employee_job_title_options(department_employees)
    reset_stale_filter_selection(
        st.session_state, job_title_key, job_title_options
    )
    job_title = filter_columns[1].selectbox(
        "岗位", job_title_options, key=job_title_key
    )

    filtered = filter_employees_by_organization(
        department_employees, job_title=job_title
    )
    if filtered.empty:
        reset_stale_employee_selection(st.session_state, employee_key, [])
        st.info("当前部门和岗位下没有可管理的员工。")
        return None

    records = {
        str(row["employee_id"]): row for row in filtered.to_dict("records")
    }
    reset_stale_employee_selection(st.session_state, employee_key, records)
    selected_id = st.selectbox(
        "选择员工", list(records),
        format_func=lambda value: employee_label(records[value]),
        key=employee_key,
    )
    return records[selected_id]
