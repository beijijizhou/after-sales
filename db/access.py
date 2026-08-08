import re

import pandas as pd


USER_ACCESS_COLUMNS = (
    "name,user_name,employee_id,department,role,is_active"
)
ACCESS_AUDIT_COLUMNS = (
    "id,user_name,old_role,new_role,old_is_active,new_is_active,"
    "changed_by,changed_at"
)
ROLE_COLUMNS = (
    "role_key,role_name,description,is_system,created_by,created_at,"
    "updated_by,updated_at"
)
PERMISSION_COLUMNS = (
    "permission_key,permission_name,permission_group,description,sort_order"
)
ROLE_PERMISSION_COLUMNS = "role_key,permission_key"
ROLE_AUDIT_COLUMNS = (
    "id,role_key,action,old_snapshot,new_snapshot,changed_by,changed_at"
)


def load_app_users(supabase):
    rows = (
        supabase.table("users")
        .select(USER_ACCESS_COLUMNS)
        .order("name")
        .execute().data
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=USER_ACCESS_COLUMNS.split(","))
    for column in ("name", "user_name", "employee_id", "department"):
        frame[column] = frame[column].map(_text)
    frame = frame.loc[frame["user_name"] != ""].copy()
    frame["role"] = frame["role"].map(_text)
    frame.loc[frame["role"] == "", "role"] = "visitor"
    frame["is_active"] = frame["is_active"].fillna(True).astype(bool)
    return frame.reset_index(drop=True)


def update_user_access(
    supabase, username, role, is_active, changed_by,
):
    validate_access_change(username, role, is_active, changed_by)
    response = supabase.rpc("update_app_user_access", {
        "p_username": str(username).strip(),
        "p_role": str(role).strip(),
        "p_is_active": bool(is_active),
        "p_changed_by": str(changed_by).strip(),
    }).execute()
    return response.data or []


def load_access_audit(supabase, limit=200):
    rows = (
        supabase.table("app_user_access_audit")
        .select(ACCESS_AUDIT_COLUMNS)
        .order("changed_at", desc=True)
        .limit(limit)
        .execute().data
    )
    return pd.DataFrame(rows)


def load_roles(supabase):
    rows = (
        supabase.table("app_roles").select(ROLE_COLUMNS)
        .order("role_name").execute().data
    )
    return pd.DataFrame(rows)


def load_permission_catalog(supabase):
    rows = (
        supabase.table("app_permissions").select(PERMISSION_COLUMNS)
        .order("sort_order").execute().data
    )
    return pd.DataFrame(rows)


def load_role_permissions(supabase):
    rows = (
        supabase.table("app_role_permissions")
        .select(ROLE_PERMISSION_COLUMNS).execute().data
    )
    return pd.DataFrame(rows)


def load_role_audit(supabase, limit=200):
    rows = (
        supabase.table("app_role_change_audit")
        .select(ROLE_AUDIT_COLUMNS)
        .order("changed_at", desc=True).limit(limit).execute().data
    )
    return pd.DataFrame(rows)


def save_role_definition(
    supabase, role_key, role_name, description, permissions, changed_by,
):
    validate_role_definition(role_key, role_name, permissions)
    response = supabase.rpc("upsert_app_role", {
        "p_role_key": str(role_key).strip().lower(),
        "p_role_name": str(role_name).strip(),
        "p_description": str(description or "").strip(),
        "p_permissions": sorted(set(permissions)),
        "p_changed_by": str(changed_by).strip(),
    }).execute()
    return response.data or []


def validate_access_change(username, role, is_active, changed_by):
    username = str(username or "").strip()
    role = str(role or "").strip()
    changed_by = str(changed_by or "").strip()
    if not username:
        raise ValueError("请选择需要修改的用户")
    if not role:
        raise ValueError("请选择角色")
    if username == changed_by:
        raise ValueError("权限管理员不能修改自己的角色或启用状态")


def validate_role_definition(role_key, role_name, permissions):
    role_key = str(role_key or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", role_key):
        raise ValueError("角色标识只能使用3–32位小写字母、数字和下划线")
    if not str(role_name or "").strip():
        raise ValueError("请填写角色名称")
    if role_key == "admin" and "can_manage_access" not in set(permissions):
        raise ValueError("管理员角色必须保留权限管理能力")


def _text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()
