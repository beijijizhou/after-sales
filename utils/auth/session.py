import streamlit as st

from db.supabase_client import supabase
from utils.auth.constants import (
    AUTH_QUERY_KEY,
    PAGE_ACCESS,
    PUBLIC_PERMISSIONS,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    ROLE_VISITOR,
)
from utils.auth.cookies import (
    queue_auth_cookie,
    queue_auth_cookie_deletion,
    read_auth_cookie,
    render_pending_auth_cookie,
)
from utils.auth.security import build_auth_token, parse_auth_token, verify_password


def get_current_user():
    cookie_action = render_pending_auth_cookie()
    if cookie_action == "delete" or st.session_state.get(
        "suppress_auth_cookie_restore"
    ):
        return st.session_state.get("current_user")
    restore_user_from_browser()
    render_pending_auth_cookie()
    return st.session_state.get("current_user")


def get_current_role():
    user = get_current_user() or {}
    return user.get("role")


def get_current_operator_name():
    user = get_current_user() or {}
    return str(
        user.get("display_name") or user.get("username") or "system"
    ).strip()


def has_permission(permission):
    user = get_current_user()
    if not user:
        return permission in PUBLIC_PERMISSIONS
    return bool(user.get(permission)) or user.get("role") == ROLE_ADMIN


def has_role(required_role):
    return get_current_role() == required_role or get_current_role() == ROLE_ADMIN


def can_access_page(page_key):
    permission = PAGE_ACCESS.get(page_key)
    return bool(permission and has_permission(permission))


def is_admin():
    return get_current_role() == ROLE_ADMIN


def load_user(username):
    response = supabase.rpc("get_app_user_login", {"p_username": username}).execute()
    if not response.data:
        return None
    return response.data[0]


def set_current_user(user):
    role = user.get("role") or ROLE_VISITOR
    permissions = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[ROLE_VISITOR])
    display_name = str(
        user.get("display_name") or user["username"]
    ).strip()
    st.session_state["current_user"] = {
        "username": user["username"],
        "display_name": display_name,
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        **permissions,
    }


def get_query_value(key):
    value = st.query_params.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def persist_login(username):
    st.session_state.pop("suppress_auth_cookie_restore", None)
    queue_auth_cookie(build_auth_token(username))
    st.session_state["persistent_login_enabled"] = True
    if AUTH_QUERY_KEY in st.query_params:
        del st.query_params[AUTH_QUERY_KEY]


def clear_persistent_login():
    st.session_state.pop("persistent_login_enabled", None)
    st.session_state["suppress_auth_cookie_restore"] = True
    queue_auth_cookie_deletion()
    if AUTH_QUERY_KEY in st.query_params:
        del st.query_params[AUTH_QUERY_KEY]


def restore_user_from_browser():
    if st.session_state.get("current_user"):
        return

    token = read_auth_cookie() or get_query_value(AUTH_QUERY_KEY)
    if not token:
        return

    username = parse_auth_token(token)
    if not username:
        clear_persistent_login()
        return

    user = load_user(username)
    if not user:
        clear_persistent_login()
        return

    set_current_user(user)
    st.session_state["persistent_login_enabled"] = True
    if get_query_value(AUTH_QUERY_KEY):
        persist_login(user["username"])


def login_user(username, password, remember=False):
    user = load_user(username.strip())
    if not user or not verify_password(password, user.get("password_hash")):
        return False

    set_current_user(user)
    if remember:
        persist_login(user["username"])
    else:
        clear_persistent_login()
    return True
