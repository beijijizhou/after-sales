import streamlit as st

from utils.auth.constants import NAV_ITEMS, PAGE_ACCESS, PUBLIC_PERMISSIONS
from utils.auth.session import (
    clear_persistent_login,
    get_current_user,
    has_permission,
    login_user,
)


def get_remembered_credentials(prefix):
    credentials = st.session_state.get("remembered_login_credentials") or {}
    return credentials.get("username", ""), credentials.get("password", "")


def update_remembered_credentials(username, password, remember):
    if remember:
        st.session_state["remembered_login_credentials"] = {
            "username": username,
            "password": password,
        }
    else:
        st.session_state.pop("remembered_login_credentials", None)


def render_login():
    st.title("登录")
    st.caption("请输入账号后继续使用系统")
    with st.form("main_login_form", clear_on_submit=False):
        username, password, remember = render_login_fields("main")
        submitted = st.form_submit_button("登录", width="stretch")
    if submitted:
        handle_login(username, password, remember, show_setup_hint=True)
    st.stop()


def render_sidebar_login():
    if get_current_user():
        return

    with st.sidebar.expander("员工登录", expanded=False):
        with st.form("sidebar_login_form", clear_on_submit=False):
            username, password, remember = render_login_fields("sidebar")
            submitted = st.form_submit_button(
                "登录", width="stretch"
            )
        if submitted:
            handle_login(username, password, remember, show_setup_hint=False)


def render_login_fields(prefix):
    remembered_username, remembered_password = get_remembered_credentials(prefix)
    username = st.text_input(
        "账号",
        value=remembered_username,
        key=f"{prefix}_login_username",
        autocomplete="username",
    )
    password = st.text_input(
        "密码",
        value=remembered_password,
        type="password",
        key=None if prefix == "main" else f"{prefix}_login_password",
        autocomplete="current-password",
    )
    remember = st.checkbox(
        "记住账号和密码",
        value=bool(remembered_username or remembered_password),
        key=f"{prefix}_remember_login",
    )
    return username, password, remember


def handle_login(username, password, remember, show_setup_hint):
    try:
        if login_user(username, password, remember):
            update_remembered_credentials(username, password, remember)
            st.rerun()
        else:
            st.error("账号或密码不正确")
    except Exception as e:
        st.error(f"登录失败：{e}")
        hint = "如果这是第一次启用登录，请先在 Supabase SQL Editor 运行 sql/access_control.sql"
        st.info(hint if show_setup_hint else "请先在 Supabase SQL Editor 运行 sql/access_control.sql")


def render_user_badge():
    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.caption(f"{user['display_name']} · {user['role_label']}")
        if st.button("退出登录", width="stretch"):
            st.session_state.pop("current_user", None)
            clear_persistent_login()
            st.rerun()


def render_navigation():
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        for page_key, label, path in NAV_ITEMS:
            permission = PAGE_ACCESS.get(page_key)
            if permission and has_permission(permission):
                st.page_link(path, label=label)

    render_user_badge()
    render_sidebar_login()


def require_login():
    if not get_current_user():
        render_login()
    render_user_badge()


def require_page_access(page_key):
    render_navigation()
    required_permission = PAGE_ACCESS.get(page_key)
    if required_permission not in PUBLIC_PERMISSIONS and not get_current_user():
        render_login()
    if required_permission and not has_permission(required_permission):
        st.error("当前账号没有权限查看这个页面")
        st.stop()


def require_action(permission="can_edit_inventory"):
    return has_permission(permission)
