import streamlit as st

from db.access import (
    load_app_users,
    load_permission_catalog,
    load_role_permissions,
    load_roles,
)
from ui.access.audit import render_access_audit
from ui.access.permissions import render_permission_overview
from ui.access.role_editor import render_role_configuration
from ui.access.user_editor import (
    access_change_preview,
    filter_access_users,
    render_user_role_editor,
    user_access_table,
)


def render_access_management_page(supabase):
    st.title("访问权限管理")
    st.caption(
        "仅权限管理员可访问。角色和权限组合来自数据库，所有修改都有审计记录。"
    )
    notice = st.session_state.pop("access_management_notice", "")
    if notice:
        st.success(notice)
    try:
        users = load_app_users(supabase)
        roles = load_roles(supabase)
        catalog = load_permission_catalog(supabase)
        assigned = load_role_permissions(supabase)
    except Exception as error:
        _render_setup_error(error)
        return

    user_tab, role_tab, matrix_tab, audit_tab = st.tabs([
        "用户角色", "角色配置", "权限矩阵", "变更记录",
    ])
    with user_tab:
        render_user_role_editor(supabase, users, roles, catalog, assigned)
    with role_tab:
        render_role_configuration(supabase, roles, catalog, assigned)
    with matrix_tab:
        render_permission_overview(roles, catalog, assigned)
    with audit_tab:
        render_access_audit(supabase, roles)


def _render_setup_error(error):
    message = str(error)
    tables = (
        "app_roles", "app_permissions", "app_role_permissions",
        "app_user_access_audit", "app_role_change_audit",
    )
    if any(table in message for table in tables):
        st.warning(
            "动态角色权限尚未初始化，请按顺序执行 "
            "sql/access/role_management/ 下的 01–12 脚本。"
        )
    else:
        st.error("权限数据暂时无法读取，请稍后重试。")
