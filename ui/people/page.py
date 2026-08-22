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
    manageable_employees,
)
from ui.people.profile import (
    render_employee_profile_editor,
    render_employee_profile_history,
)
from ui.people.status import (
    render_employee_status_action,
    render_employee_status_history,
)
from ui.people.selector import render_employee_selector
from utils.auth import get_current_user, has_permission


def render_people_management_page(supabase):
    st.title("人员管理")
    notice = st.session_state.pop("people_management_notice", "")
    if notice:
        st.success(notice)

    can_register = has_permission("can_register")
    can_manage = has_permission("can_manage_people")
    if can_manage:
        try:
            employees = manageable_employees(
                load_employees(supabase), get_current_user()
            )
        except Exception:
            st.error("员工资料暂时无法读取，请稍后重试。")
            return
        status_tab, action_tab, registration_tab, history_tab = st.tabs([
            "人员状态", "人员办理", "新增员工", "变更记录",
        ])
        with status_tab:
            _render_roster(employees)
        with action_tab:
            _render_people_action(supabase, employees)
        with registration_tab:
            _render_registration(supabase, can_register)
        with history_tab:
            _render_people_history(supabase, employees)
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


def _render_roster(employees):
    user = get_current_user() or {}
    if user.get("role") != "admin":
        st.caption("仅显示你负责生产部门内、职级低于你的员工。")
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


def _render_people_action(supabase, employees):
    st.subheader("选择员工并办理")
    selected = render_employee_selector(employees, "people_action")
    if selected is None:
        return
    action = st.segmented_control(
        "办理事项", ["离职/复职", "人员调岗"], default="离职/复职",
        key="people_action_type",
    )
    st.divider()
    if action == "离职/复职":
        render_employee_status_action(supabase, selected=selected)
    else:
        render_employee_profile_editor(supabase, selected=selected)


def _render_people_history(supabase, employees):
    employee_ids = employees["employee_id"].astype(str).tolist()
    history_type = st.segmented_control(
        "记录类型", ["离职/复职", "人员调岗"], default="离职/复职",
        key="people_history_type",
    )
    if history_type == "离职/复职":
        render_employee_status_history(supabase, employee_ids)
    else:
        render_employee_profile_history(supabase, employee_ids)
