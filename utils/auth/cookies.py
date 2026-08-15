from datetime import datetime, timedelta
import threading

import extra_streamlit_components as stx
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx


AUTH_COOKIE_NAME = "after_sales_auth"
COOKIE_LIFETIME_DAYS = 30
PENDING_COOKIE_ACTION = "pending_auth_cookie_action"
AUTH_COOKIE_CACHE = "auth_cookie_cached_value"
_COOKIE_READER_LOCAL = threading.local()


def read_auth_cookie():
    cached = st.session_state.get(AUTH_COOKIE_CACHE)
    if cached:
        return cached
    manager = _cookie_reader_manager()
    value = None
    try:
        value = manager.get(AUTH_COOKIE_NAME)
    except Exception:
        value = None
    if value:
        st.session_state[AUTH_COOKIE_CACHE] = value
        return value
    try:
        cookies = manager.get_all() or {}
    except Exception:
        cookies = {}
    value = cookies.get(AUTH_COOKIE_NAME) or st.context.cookies.get(
        AUTH_COOKIE_NAME
    )
    # CookieManager is a frontend component. On a fresh Cloud session its
    # first render can return before browser cookies arrive, then trigger a
    # rerun. Never cache that temporary empty result or the rerun cannot
    # restore the login.
    if value:
        st.session_state[AUTH_COOKIE_CACHE] = value
    return value


def queue_auth_cookie(token):
    st.session_state.pop(AUTH_COOKIE_CACHE, None)
    st.session_state[PENDING_COOKIE_ACTION] = ("write", token)


def queue_auth_cookie_deletion():
    st.session_state.pop(AUTH_COOKIE_CACHE, None)
    st.session_state[PENDING_COOKIE_ACTION] = ("delete", "")


def render_pending_auth_cookie():
    action = st.session_state.pop(PENDING_COOKIE_ACTION, None)
    if not action:
        return None

    operation, token = action
    if operation == "delete":
        _delete_auth_cookie()
    else:
        _write_auth_cookie(token)
    return operation


def _write_auth_cookie(token):
    manager = stx.CookieManager(key="auth_cookie_writer")
    manager.set(
        AUTH_COOKIE_NAME,
        token,
        key="set_after_sales_auth",
        path="/",
        expires_at=datetime.now() + timedelta(days=COOKIE_LIFETIME_DAYS),
        same_site="lax",
    )
    st.session_state[AUTH_COOKIE_CACHE] = token


def _delete_auth_cookie():
    manager = stx.CookieManager(key="auth_cookie_deleter")
    manager.delete(AUTH_COOKIE_NAME, key="delete_after_sales_auth")
    st.session_state[AUTH_COOKIE_CACHE] = None


def _cookie_reader_manager():
    context = get_script_run_ctx()
    if (
        context is not None
        and getattr(_COOKIE_READER_LOCAL, "context", None) is context
    ):
        return _COOKIE_READER_LOCAL.manager
    manager = stx.CookieManager(key="auth_cookie_reader")
    if context is not None:
        _COOKIE_READER_LOCAL.context = context
        _COOKIE_READER_LOCAL.manager = manager
    return manager
