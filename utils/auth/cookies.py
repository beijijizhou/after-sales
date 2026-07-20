from datetime import datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st


AUTH_COOKIE_NAME = "after_sales_auth"
COOKIE_LIFETIME_DAYS = 30
PENDING_COOKIE_ACTION = "pending_auth_cookie_action"


def read_auth_cookie():
    return st.context.cookies.get(AUTH_COOKIE_NAME)


def queue_auth_cookie(token):
    st.session_state[PENDING_COOKIE_ACTION] = ("write", token)


def queue_auth_cookie_deletion():
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
        same_site="strict",
    )


def _delete_auth_cookie():
    manager = stx.CookieManager(key="auth_cookie_deleter")
    manager.delete(AUTH_COOKIE_NAME, key="delete_after_sales_auth")
