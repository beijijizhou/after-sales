import streamlit as st

from db.supabase_client import supabase
from utils.auth.constants import (
    AUTH_QUERY_KEY,
    PAGE_ACCESS,
    PUBLIC_PERMISSIONS,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_VISITOR,
)
from utils.auth.security import build_auth_token, parse_auth_token, verify_password


def get_current_user():
    restore_user_from_query()
    ensure_persistent_login_query()
    return st.session_state.get("current_user")


def get_current_role():
    user = get_current_user() or {}
    return user.get("role")


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
    st.session_state["current_user"] = {
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": role,
        "role_label": user.get("role_label") or ROLE_LABELS.get(role, role),
        "can_view_app": bool(user.get("can_view_app")),
        "can_register": bool(user.get("can_register")),
        "can_view_qa": bool(user.get("can_view_qa")),
        "can_view_hotstamp": bool(user.get("can_view_hotstamp")),
        "can_view_platform": bool(user.get("can_view_platform")),
        "can_view_inventory": bool(user.get("can_view_inventory")),
        "can_edit_inventory": bool(user.get("can_edit_inventory")),
        "can_view_container": bool(user.get("can_view_container")),
        "can_edit_container": bool(user.get("can_edit_container")),
        "can_input_after_sales": bool(user.get("can_input_after_sales")),
        "can_view_cost": bool(user.get("can_view_cost")),
    }


def get_query_value(key):
    value = st.query_params.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def persist_login(username):
    st.query_params[AUTH_QUERY_KEY] = build_auth_token(username)
    st.session_state["persistent_login_enabled"] = True


def clear_persistent_login():
    st.session_state.pop("persistent_login_enabled", None)
    if AUTH_QUERY_KEY in st.query_params:
        del st.query_params[AUTH_QUERY_KEY]


def ensure_persistent_login_query():
    user = st.session_state.get("current_user")
    if not user or not st.session_state.get("persistent_login_enabled"):
        return
    if get_query_value(AUTH_QUERY_KEY):
        return

    persist_login(user["username"])


def restore_user_from_query():
    if st.session_state.get("current_user"):
        return

    token = get_query_value(AUTH_QUERY_KEY)
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
