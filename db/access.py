import pandas as pd

from utils.auth.constants import ROLE_LABELS


USER_ACCESS_COLUMNS = (
    "name,user_name,employee_id,department,role,is_active"
)
ACCESS_AUDIT_COLUMNS = (
    "id,user_name,old_role,new_role,old_is_active,new_is_active,"
    "changed_by,changed_at"
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
    frame["role"] = frame["role"].fillna("visitor").astype(str)
    frame["is_active"] = frame["is_active"].fillna(True).astype(bool)
    return frame


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


def validate_access_change(username, role, is_active, changed_by):
    username = str(username or "").strip()
    role = str(role or "").strip()
    changed_by = str(changed_by or "").strip()
    if not username:
        raise ValueError("请选择需要修改的用户")
    if role not in ROLE_LABELS:
        raise ValueError(f"不支持的角色：{role}")
    if username == changed_by and (role != "admin" or not is_active):
        raise ValueError("管理员不能停用或移除自己的管理员角色")
