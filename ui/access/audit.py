import streamlit as st

from db.access import (
    load_access_audit,
    load_employee_account_audit,
    load_role_audit,
)
from ui.access.permissions import role_labels


def render_access_audit(supabase, roles):
    labels = role_labels(roles)
    st.subheader("用户角色变更")
    try:
        audit = load_access_audit(supabase)
        role_audit = load_role_audit(supabase)
    except Exception:
        st.warning("权限审计暂时无法读取，请确认动态角色迁移已经安装。")
        return
    if audit.empty:
        st.info("尚无用户角色变更记录。")
    else:
        display = audit.rename(columns={
            "user_name": "账号", "old_role": "原角色", "new_role": "新角色",
            "old_is_active": "原启用状态", "new_is_active": "新启用状态",
            "changed_by": "操作人", "changed_at": "操作时间",
        }).copy()
        for column in ("原角色", "新角色"):
            display[column] = display[column].map(
                lambda role: labels.get(str(role), str(role))
            )
        for column in ("原启用状态", "新启用状态"):
            display[column] = display[column].map({True: "启用", False: "停用"})
        st.dataframe(display[[
            "账号", "原角色", "新角色", "原启用状态", "新启用状态",
            "操作人", "操作时间",
        ]], hide_index=True, width="stretch")

    st.subheader("角色配置变更")
    if role_audit.empty:
        st.info("尚无角色配置变更记录。")
    else:
        display = role_audit.rename(columns={
            "role_key": "角色标识", "action": "操作",
            "old_snapshot": "修改前", "new_snapshot": "修改后",
            "changed_by": "操作人", "changed_at": "操作时间",
        }).copy()
        display["操作"] = display["操作"].map({
            "create": "创建", "update": "修改",
        }).fillna(display["操作"])
        st.dataframe(display[[
            "角色标识", "操作", "修改前", "修改后", "操作人", "操作时间",
        ]], hide_index=True, width="stretch")

    st.subheader("员工账号与升职记录")
    try:
        account_audit = load_employee_account_audit(supabase)
    except Exception:
        st.info("执行第 16 个权限迁移后，这里会显示员工账号与升职记录。")
        return
    if account_audit.empty:
        st.info("尚无员工账号与升职记录。")
        return
    display = account_audit.rename(columns={
        "employee_name": "员工", "old_username": "原账号",
        "new_username": "新账号", "password_reset": "密码已重置",
        "old_role": "原角色", "new_role": "新角色",
        "old_job_title": "原岗位", "new_job_title": "新岗位",
        "old_departments": "原生产部门", "new_departments": "新生产部门",
        "changed_by": "操作人", "changed_at": "操作时间",
    }).copy()
    for column in ("原生产部门", "新生产部门"):
        display[column] = display[column].map(
            lambda values: " / ".join(values or [])
        )
    display["密码已重置"] = display["密码已重置"].map({
        True: "是", False: "否",
    })
    st.dataframe(display[[
        "员工", "原账号", "新账号", "密码已重置", "原角色", "新角色",
        "原岗位", "新岗位", "原生产部门", "新生产部门", "操作人", "操作时间",
    ]], hide_index=True, width="stretch")
