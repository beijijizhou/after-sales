import pandas as pd
import streamlit as st

from db.access import (
    load_access_audit,
    load_app_users,
    update_user_access,
    validate_access_change,
)
from ui.access.permissions import permission_matrix, permission_names
from utils.auth import get_current_user
from utils.auth.constants import ROLE_LABELS, ROLE_PERMISSIONS


def render_access_management_page(supabase):
    st.title("访问权限管理")
    st.caption("仅管理员可访问。角色决定页面和操作权限，修改会写入审计记录。")
    notice = st.session_state.pop("access_management_notice", "")
    if notice:
        st.success(notice)

    try:
        users = load_app_users(supabase)
    except Exception as error:
        _render_setup_error(error)
        return

    role_tab, matrix_tab, audit_tab = st.tabs([
        "用户角色", "角色权限说明", "变更记录",
    ])
    with role_tab:
        _render_user_role_editor(supabase, users)
    with matrix_tab:
        _render_permission_matrix()
    with audit_tab:
        _render_access_audit(supabase)


def _render_user_role_editor(supabase, users):
    active_count = int(users["is_active"].sum()) if not users.empty else 0
    metrics = st.columns(3)
    metrics[0].metric("用户总数", len(users))
    metrics[1].metric("启用账号", active_count)
    metrics[2].metric(
        "主管账号",
        int((users["role"] == "supervisor").sum()) if not users.empty else 0,
    )
    st.dataframe(
        user_access_table(users), hide_index=True, width="stretch",
    )
    if users.empty:
        st.info("当前没有可管理的用户。")
        return

    options = users["user_name"].astype(str).tolist()
    labels = {
        str(row["user_name"]): (
            f"{row.get('name') or row['user_name']} · {row['user_name']}"
        )
        for row in users.to_dict("records")
    }
    selected_username = st.selectbox(
        "选择用户", options, format_func=labels.get,
        key="access_management_user",
    )
    selected = users.loc[
        users["user_name"].astype(str) == selected_username
    ].iloc[0].to_dict()
    role_options = list(ROLE_LABELS)
    role_index = role_options.index(selected["role"])
    form_key = f"access_role_form_{selected_username}"
    with st.form(form_key):
        new_role = st.selectbox(
            "角色", role_options, index=role_index,
            format_func=ROLE_LABELS.get,
            key=f"access_role_value_{selected_username}",
        )
        new_active = st.checkbox(
            "账号启用", value=bool(selected["is_active"]),
            key=f"access_active_value_{selected_username}",
        )
        preview = access_change_preview(selected, new_role, new_active)
        st.caption("修改预览")
        st.dataframe(pd.DataFrame([preview]), hide_index=True, width="stretch")
        confirmed = st.checkbox("我已核对用户、角色和权限变化")
        submitted = st.form_submit_button(
            "保存权限变更", type="primary", width="stretch",
            disabled=not confirmed or not preview["是否变化"],
        )
    if not submitted:
        return

    actor = str((get_current_user() or {}).get("username") or "").strip()
    try:
        validate_access_change(
            selected_username, new_role, new_active, actor
        )
        update_user_access(
            supabase, selected_username, new_role, new_active, actor
        )
    except Exception as error:
        st.error(_access_error_message(error))
        return
    st.session_state["access_management_notice"] = (
        f"已更新 {labels[selected_username]}："
        f"{ROLE_LABELS[new_role]} / {'启用' if new_active else '停用'}"
    )
    st.rerun()


def user_access_table(users):
    if users.empty:
        return pd.DataFrame(columns=["姓名", "账号", "部门", "角色", "状态"])
    result = users.rename(columns={
        "name": "姓名", "user_name": "账号", "employee_id": "员工编号",
        "department": "部门", "role": "角色", "is_active": "状态",
    }).copy()
    result["角色"] = result["角色"].map(ROLE_LABELS).fillna(result["角色"])
    result["状态"] = result["状态"].map({True: "启用", False: "停用"})
    return result[["姓名", "账号", "员工编号", "部门", "角色", "状态"]]


def access_change_preview(user, new_role, new_active):
    old_role = str(user.get("role") or "visitor")
    old_permissions = ROLE_PERMISSIONS.get(old_role, set())
    new_permissions = ROLE_PERMISSIONS.get(new_role, set())
    added = sorted(new_permissions - old_permissions)
    removed = sorted(old_permissions - new_permissions)
    return {
        "账号": str(user.get("user_name") or ""),
        "原角色": ROLE_LABELS.get(old_role, old_role),
        "新角色": ROLE_LABELS.get(new_role, new_role),
        "原状态": "启用" if user.get("is_active") else "停用",
        "新状态": "启用" if new_active else "停用",
        "新增权限": permission_names(added) or "无",
        "移除权限": permission_names(removed) or "无",
        "是否变化": old_role != new_role or bool(user.get("is_active")) != new_active,
    }


def _render_permission_matrix():
    st.info(
        "这里展示角色的实际权限。用户只能分配角色，不能在此覆盖单项权限，"
        "避免同名角色在不同账号上产生不可追踪的差异。"
    )
    st.dataframe(permission_matrix(), hide_index=True, width="stretch")


def _render_access_audit(supabase):
    try:
        audit = load_access_audit(supabase)
    except Exception as error:
        _render_setup_error(error)
        return
    if audit.empty:
        st.info("尚无权限变更记录。")
        return
    display = audit.rename(columns={
        "user_name": "账号", "old_role": "原角色", "new_role": "新角色",
        "old_is_active": "原启用状态", "new_is_active": "新启用状态",
        "changed_by": "操作人", "changed_at": "操作时间",
    }).copy()
    for column in ("原角色", "新角色"):
        display[column] = display[column].map(ROLE_LABELS).fillna(display[column])
    for column in ("原启用状态", "新启用状态"):
        display[column] = display[column].map({True: "启用", False: "停用"})
    st.dataframe(
        display[[
            "账号", "原角色", "新角色", "原启用状态", "新启用状态",
            "操作人", "操作时间",
        ]],
        hide_index=True,
        width="stretch",
    )


def _access_error_message(error):
    message = str(error)
    if "update_app_user_access" in message:
        return "权限管理数据库函数尚未安装，请运行 sql/access/02_role_management.sql。"
    return message


def _render_setup_error(error):
    message = str(error)
    if "app_user_access_audit" in message or "update_app_user_access" in message:
        st.warning("权限管理尚未初始化，请运行 sql/access/02_role_management.sql。")
    else:
        st.error("权限数据暂时无法读取，请稍后重试。")
