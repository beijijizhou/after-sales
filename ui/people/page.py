import streamlit as st

from db.access import (
    create_employee,
    load_employees,
    load_production_departments,
)
from ui.people.models import (
    employee_creation_error_message,
    employee_table,
    filter_employees,
)
from ui.people.profile import (
    render_employee_profile_editor,
    render_employee_profile_history,
)
from ui.people.status import (
    render_employee_status_action,
    render_employee_status_history,
)
from utils.auth import has_permission


def render_people_management_page(supabase):
    st.title("人员管理")
    notice = st.session_state.pop("people_management_notice", "")
    if notice:
        st.success(notice)

    can_register = has_permission("can_register")
    can_manage = has_permission("can_manage_people")
    if can_manage:
        roster_tab, registration_tab, history_tab = st.tabs([
            "员工名单", "新增员工", "人员变更记录",
        ])
        with roster_tab:
            _render_roster(supabase)
        with registration_tab:
            _render_registration(supabase, can_register)
        with history_tab:
            _render_people_history(supabase)
        return

    st.caption("在这里登记新员工。离职与恢复在职由组长或人员管理员办理。")
    _render_registration(supabase, can_register)


def _render_registration(supabase, can_register):
    st.subheader("新增员工")
    if not can_register:
        st.info("当前账号只能查看，不能新增员工。")
        return
    departments = load_production_departments(supabase)
    with st.form("employee_registration_form", clear_on_submit=True):
        name = st.text_input("姓名")
        job_title = st.selectbox("岗位", ["质检", "烫印"])
        selected_departments = st.multiselect(
            "生产部门（可多选）", departments,
            default=["DTF"] if "DTF" in departments else departments[:1],
        )
        is_qa = job_title == "质检"
        username = st.text_input("登录账号用户名", disabled=not is_qa)
        password = st.text_input("密码", type="password", disabled=not is_qa)
        submitted = st.form_submit_button("新增员工", type="primary")
    if not submitted:
        return
    try:
        create_employee(
            supabase, name, job_title, selected_departments,
            username=username if is_qa else "",
            password=password if is_qa else "",
        )
    except Exception as error:
        st.error(employee_creation_error_message(error))
        return
    st.session_state["people_management_notice"] = f"已新增员工：{name.strip()}"
    st.rerun()


def _render_roster(supabase):
    try:
        employees = load_employees(supabase)
    except Exception:
        st.error("员工资料暂时无法读取，请稍后重试。")
        return
    active_count = int(employees["is_active"].sum()) if not employees.empty else 0
    metrics = st.columns(3)
    metrics[0].metric("员工总数", len(employees))
    metrics[1].metric("在职", active_count)
    metrics[2].metric("已离职", len(employees) - active_count)

    status_filter = st.segmented_control(
        "人员状态", ["在职", "已离职", "全部"], default="在职",
        key="people_status_filter",
    )
    filtered = filter_employees(employees, status_filter)
    st.dataframe(employee_table(filtered), hide_index=True, width="stretch")
    if filtered.empty:
        st.info("当前状态下没有员工。")
        return
    profile_tab, status_tab = st.tabs(["资料调整", "离职/复职"])
    with profile_tab:
        render_employee_profile_editor(supabase, filtered)
    with status_tab:
        render_employee_status_action(supabase, filtered)


def _render_people_history(supabase):
    profile_tab, status_tab = st.tabs(["资料调整", "离职/复职"])
    with profile_tab:
        render_employee_profile_history(supabase)
    with status_tab:
        render_employee_status_history(supabase)
