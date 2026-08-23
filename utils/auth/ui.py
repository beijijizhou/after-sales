import base64
from pathlib import Path

import streamlit as st

import utils.auth.constants as auth_constants
from utils.auth.session import (
    clear_persistent_login,
    can_access_page,
    get_current_user,
    has_permission,
    login_user,
)


BRAND_LOGO = (
    Path(__file__).resolve().parents[2]
    / "assets" / "brand" / "production-logo.jpg"
)


@st.cache_data(show_spinner=False)
def _brand_logo_data_url():
    encoded = base64.b64encode(BRAND_LOGO.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_brand_header():
    logo_url = _brand_logo_data_url()
    with st.sidebar:
        st.markdown(
            f"""
            <div class="app-brand">
                <div class="app-brand__mark">
                    <img src="{logo_url}" alt="生产管理系统 Logo">
                </div>
                <div>
                    <div class="app-brand__name">生产管理系统</div>
                    <div class="app-brand__sub">Production OS</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


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

    with st.sidebar:
        st.caption("当前身份：游客")
        with st.expander("员工登录", expanded=False):
            with st.form("sidebar_login_form", clear_on_submit=False):
                username, password, remember = render_login_fields("sidebar")
                submitted = st.form_submit_button(
                    "登录", width="stretch"
                )
            if submitted:
                handle_login(
                    username, password, remember, show_setup_hint=False
                )


def render_login_fields(prefix):
    username = st.text_input(
        "账号",
        key=f"{prefix}_login_username",
        autocomplete="username",
    )
    password = st.text_input(
        "密码",
        type="password",
        key=f"{prefix}_login_password",
        autocomplete="current-password",
    )
    remember = st.checkbox(
        "保持登录（30天）",
        value=True,
        key=f"{prefix}_remember_login",
    )
    return username, password, remember


def handle_login(username, password, remember, show_setup_hint):
    try:
        if login_user(username, password, remember):
            st.rerun()
        else:
            st.error("账号或密码不正确")
    except Exception as e:
        st.error(f"登录失败：{e}")
        hint = "如果这是第一次启用登录，请先在 Supabase SQL Editor 运行 sql/access/access_control.sql"
        st.info(hint if show_setup_hint else "请先在 Supabase SQL Editor 运行 sql/access/access_control.sql")


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
    constants = auth_constants
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

    render_brand_header()
    render_user_badge()
    render_sidebar_login()

    visible_sections = visible_navigation_sections(
        constants.NAV_SECTIONS, constants.PAGE_ACCESS, can_access_page
    )
    with st.sidebar:
        st.divider()
        for section_title, visible_items in visible_sections:
            if section_title and len(visible_items) > 1:
                with st.expander(section_title, expanded=False):
                    for _, label, path in visible_items:
                        st.page_link(path, label=label)
                continue
            for _, label, path in visible_items:
                st.page_link(path, label=label)


def visible_navigation_sections(sections, page_access, access_check):
    result = []
    for section_title, section_items in sections:
        visible_items = [
            (page_key, label, path)
            for page_key, label, path in section_items
            if page_access.get(page_key) and access_check(page_key)
        ]
        if visible_items:
            result.append((section_title, visible_items))
    return result


def require_login():
    if not get_current_user():
        render_login()
    render_user_badge()


def require_page_access(page_key):
    constants = auth_constants
    render_navigation()
    required_permission = constants.PAGE_ACCESS.get(page_key)
    required_permissions = (
        required_permission
        if isinstance(required_permission, (tuple, list, set))
        else (required_permission,)
    )
    if (
        not any(
            permission in constants.PUBLIC_PERMISSIONS
            for permission in required_permissions
        )
        and not get_current_user()
    ):
        render_login()
    if required_permission and not can_access_page(page_key):
        st.error("当前账号没有权限查看这个页面")
        st.stop()


def require_action(permission="can_edit_inventory"):
    return has_permission(permission)
