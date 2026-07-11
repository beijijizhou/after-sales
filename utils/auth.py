import base64
import hashlib
import hmac
import os

import streamlit as st

from db.supabase_client import supabase


ROLE_VISITOR = "visitor"
ROLE_SUPERVISOR = "supervisor"
ROLE_WAREHOUSE = "warehouse"
ROLE_AFTER_SALES = "after_sales"
ROLE_ADMIN = "admin"

ROLE_LABELS = {
    ROLE_VISITOR: "游客",
    ROLE_SUPERVISOR: "主管",
    ROLE_WAREHOUSE: "仓库",
    ROLE_AFTER_SALES: "售后",
    ROLE_ADMIN: "管理员",
}

PAGE_ACCESS = {
    "app": "can_view_app",
    "register": "can_register",
    "qa": "can_view_qa",
    "hotstamp": "can_view_hotstamp",
    "platform": "can_view_platform",
    "inventory": "can_view_inventory",
    "container": "can_view_container",
}

PUBLIC_PERMISSIONS = {
    "can_register",
    "can_view_qa",
    "can_view_hotstamp",
    "can_view_platform",
}

NAV_ITEMS = [
    ("app", "售后查询", "app.py"),
    ("register", "注册", "pages/0_注册.py"),
    ("qa", "质检", "pages/1_质检.py"),
    ("hotstamp", "烫印", "pages/2_烫印.py"),
    ("platform", "平台", "pages/3_平台.py"),
    ("inventory", "库存", "pages/4_库存.py"),
    ("container", "货柜安排", "pages/5_货柜安排.py"),
]


AUTH_QUERY_KEY = "auth"


def hash_password(password):
    salt = base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8").rstrip("=")
    iterations = 260000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    password_hash = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return f"pbkdf2_sha256${iterations}${salt}${password_hash}"


def verify_password(password, stored_hash):
    if not stored_hash:
        return False

    if not str(stored_hash).startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(str(stored_hash), password)

    try:
        _, iterations, salt, password_hash = str(stored_hash).split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        expected_hash = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        return hmac.compare_digest(expected_hash, password_hash)
    except Exception:
        return False


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
    response = (
        supabase
        .rpc("get_app_user_login", {"p_username": username})
        .execute()
    )
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


def get_auth_secret():
    return str(st.secrets.get("AUTH_TOKEN_SECRET") or st.secrets.get("SUPABASE_KEY") or "after-sales")


def build_auth_token(username):
    username = str(username).strip()
    signature = hmac.new(
        get_auth_secret().encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = f"{username}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def parse_auth_token(token):
    try:
        padded_token = token + "=" * (-len(token) % 4)
        payload = base64.urlsafe_b64decode(padded_token.encode("utf-8")).decode("utf-8")
        username, signature = payload.rsplit(":", 1)
        expected_signature = hmac.new(
            get_auth_secret().encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return username
    except Exception:
        return None


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

    remembered_username, remembered_password = get_remembered_credentials("main")
    username = st.text_input("账号", value=remembered_username, autocomplete="username")
    password = st.text_input(
        "密码",
        value=remembered_password,
        type="password",
        autocomplete="current-password",
    )
    remember = st.checkbox(
        "记住账号和密码",
        value=bool(remembered_username or remembered_password),
        key="main_remember_login",
    )
    if st.button("登录", use_container_width=True):
        try:
            if login_user(username, password, remember):
                update_remembered_credentials(username, password, remember)
                st.rerun()
            else:
                st.error("账号或密码不正确")
        except Exception as e:
            st.error(f"登录失败：{e}")
            st.info("如果这是第一次启用登录，请先在 Supabase SQL Editor 运行 sql/access_control.sql")
    st.stop()


def render_sidebar_login():
    if get_current_user():
        return

    with st.sidebar.expander("员工登录", expanded=False):
        remembered_username, remembered_password = get_remembered_credentials("sidebar")
        username = st.text_input(
            "账号",
            value=remembered_username,
            key="sidebar_login_username",
            autocomplete="username",
        )
        password = st.text_input(
            "密码",
            value=remembered_password,
            type="password",
            key="sidebar_login_password",
            autocomplete="current-password",
        )
        remember = st.checkbox(
            "记住账号和密码",
            value=bool(remembered_username or remembered_password),
            key="sidebar_remember_login",
        )
        if st.button("登录", use_container_width=True, key="sidebar_login_button"):
            try:
                if login_user(username, password, remember):
                    update_remembered_credentials(username, password, remember)
                    st.rerun()
                else:
                    st.error("账号或密码不正确")
            except Exception as e:
                st.error(f"登录失败：{e}")
                st.info("请先在 Supabase SQL Editor 运行 sql/access_control.sql")


def render_user_badge():
    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.caption(f"{user['display_name']} · {user['role_label']}")
        if st.button("退出登录", use_container_width=True):
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
