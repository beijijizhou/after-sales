from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.access import load_employee_status_audit, update_employee_status
from ui.people.models import employee_label
from ui.people.selector import render_employee_selector
from utils.auth import get_current_user


NEW_YORK = ZoneInfo("America/New_York")


def render_employee_status_action(supabase, employees):
    selected = render_employee_selector(employees, "people_status")
    if selected is None:
        return
    selected_id = str(selected["employee_id"])
    new_active = not bool(selected["is_active"])
    action = "恢复在职" if new_active else "办理离职"
    today = datetime.now(NEW_YORK).date()
    effective_date = st.date_input(
        "生效日期", value=today, max_value=today,
        key=f"people_status_date_{selected_id}",
    )
    reason = st.text_area(
        "变更原因" + ("（必填）" if not new_active else ""),
        placeholder="例如：员工主动离职" if not new_active else "例如：重新入职",
        key=f"people_status_reason_{selected_id}",
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
    confirmed = st.checkbox(
        f"我已核对并确认{action}",
        key=f"people_status_confirmed_{selected_id}",
    )
    submitted = st.button(
        action, type="primary", disabled=not confirmed,
        key=f"people_status_submit_{selected_id}",
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


def render_employee_status_history(supabase, employee_ids=None):
    try:
        rows = load_employee_status_audit(supabase)
    except Exception as error:
        if "app_employee_status_audit" in str(error):
            st.info("执行人员管理数据库脚本后，这里会显示离职与恢复在职记录。")
        else:
            st.error("人员变更记录暂时无法读取，请稍后重试。")
        return
    if employee_ids is not None:
        rows = rows.loc[
            rows["employee_id"].astype(str).isin({
                str(value) for value in employee_ids
            })
        ].reset_index(drop=True)
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
    st.dataframe(display[[
        "员工", "账号", "原状态", "新状态", "生效日期",
        "原因", "操作人", "操作时间",
    ]], hide_index=True, width="stretch")
