from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.access import (
    create_employee,
    load_employee_status_audit,
    load_employees,
    load_production_departments,
    update_employee_status,
)
from ui.people.models import employee_label, employee_table, filter_employees
from utils.auth import get_current_user, has_permission


NEW_YORK = ZoneInfo("America/New_York")


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
            _render_status_history(supabase)
        return

    st.caption("在这里登记新员工。离职与恢复在职由人员管理员办理。")
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
        st.error(f"员工创建失败：{error}")
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
    _render_status_action(supabase, filtered)


def _render_status_action(supabase, employees):
    options = employees["employee_id"].astype(str).tolist()
    records = {
        str(row["employee_id"]): row for row in employees.to_dict("records")
    }
    selected_id = st.selectbox(
        "选择员工", options,
        format_func=lambda value: employee_label(records[str(value)]),
        key="people_selected_employee",
    )
    selected = records[selected_id]
    new_active = not bool(selected["is_active"])
    action = "恢复在职" if new_active else "办理离职"
    today = datetime.now(NEW_YORK).date()
    with st.form(f"employee_status_form_{selected_id}"):
        effective_date = st.date_input(
            "生效日期", value=today, max_value=today,
        )
        reason = st.text_area(
            "变更原因" + ("（必填）" if not new_active else ""),
            placeholder="例如：员工主动离职" if not new_active else "例如：重新入职",
        )
        preview = pd.DataFrame([{
            "员工": employee_label(selected),
            "原状态": "在职" if selected["is_active"] else "已离职",
            "新状态": "在职" if new_active else "已离职",
            "生效日期": effective_date,
            "原因": reason.strip() or "未填写",
        }])
        st.caption("变更预览")
        st.dataframe(preview, hide_index=True, width="stretch")
        confirmed = st.checkbox(f"我已核对并确认{action}")
        submitted = st.form_submit_button(
            action, type="primary", disabled=not confirmed,
        )
    if not submitted:
        return
    actor = str((get_current_user() or {}).get("username") or "").strip()
    try:
        update_employee_status(
            supabase, selected_id, new_active, effective_date, reason, actor,
        )
    except Exception as error:
        message = str(error)
        if "update_employee_employment_status" in message:
            st.error(
                "人员离职功能尚未初始化，请执行 "
                "sql/access/role_management/12_people_management.sql。"
            )
        else:
            st.error(message)
        return
    st.session_state["people_management_notice"] = (
        f"已为 {selected['name']} {action}，生效日期 {effective_date:%Y-%m-%d}。"
    )
    st.rerun()


def _render_status_history(supabase):
    try:
        rows = load_employee_status_audit(supabase)
    except Exception as error:
        if "app_employee_status_audit" in str(error):
            st.info("执行人员管理数据库脚本后，这里会显示离职与恢复在职记录。")
        else:
            st.error("人员变更记录暂时无法读取，请稍后重试。")
        return
    if rows.empty:
        st.info("暂无人员状态变更记录。")
        return
    display = rows.rename(columns={
        "employee_name": "员工", "user_name": "账号",
        "old_is_active": "原状态", "new_is_active": "新状态",
        "effective_date": "生效日期", "reason": "原因",
        "changed_by": "操作人", "changed_at": "操作时间",
    }).copy()
    for column in ("原状态", "新状态"):
        display[column] = display[column].map({True: "在职", False: "已离职"})
    st.dataframe(
        display[[
            "员工", "账号", "原状态", "新状态", "生效日期",
            "原因", "操作人", "操作时间",
        ]], hide_index=True, width="stretch",
    )
