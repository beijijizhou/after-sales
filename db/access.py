import re

import pandas as pd


USER_ACCESS_COLUMNS = (
    "name,user_name,employee_id,department,job_title,role,is_active"
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
EMPLOYEE_STATUS_AUDIT_COLUMNS = (
    "id,employee_id,employee_name,user_name,old_is_active,new_is_active,"
    "effective_date,reason,changed_by,changed_at"
)


def load_app_users(supabase):
    try:
        rows = (
            supabase.table("users").select(USER_ACCESS_COLUMNS)
            .order("name").execute().data
        )
    except Exception as error:
        if "job_title" not in str(error):
            raise
        rows = (
            supabase.table("users")
            .select(USER_ACCESS_COLUMNS.replace(",job_title", ""))
            .order("name").execute().data
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=USER_ACCESS_COLUMNS.split(","))
    for column in ("name", "user_name", "employee_id", "department"):
        frame[column] = frame[column].map(_text)
    if "job_title" not in frame:
        frame["job_title"] = frame["department"]
    frame["job_title"] = frame["job_title"].map(_text).where(
        frame["job_title"].map(_text) != "", frame["department"]
    )
    frame = frame.loc[frame["user_name"] != ""].copy()
    frame["role"] = frame["role"].map(_text)
    frame.loc[frame["role"] == "", "role"] = "visitor"
    frame["is_active"] = frame["is_active"].fillna(True).astype(bool)
    frame["departments"] = _load_user_departments(supabase, frame)
    return frame.reset_index(drop=True)


def load_employees(supabase):
    """Load every employee, including staff without a login account."""
    try:
        rows = (
            supabase.table("users").select(USER_ACCESS_COLUMNS)
            .order("name").execute().data
        )
    except Exception as error:
        if "job_title" not in str(error):
            raise
        rows = (
            supabase.table("users")
            .select(USER_ACCESS_COLUMNS.replace(",job_title", ""))
            .order("name").execute().data
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        columns = USER_ACCESS_COLUMNS.split(",") + ["departments"]
        return pd.DataFrame(columns=columns)
    for column in ("name", "user_name", "employee_id", "department"):
        frame[column] = frame[column].map(_text)
    if "job_title" not in frame:
        frame["job_title"] = frame["department"]
    frame["job_title"] = frame["job_title"].map(_text).where(
        frame["job_title"].map(_text) != "", frame["department"]
    )
    frame["role"] = frame["role"].map(_text)
    frame.loc[frame["role"] == "", "role"] = "visitor"
    frame["is_active"] = frame["is_active"].fillna(True).astype(bool)
    frame["departments"] = _load_user_departments(supabase, frame)
    return frame.reset_index(drop=True)


def update_user_access(
    supabase, username, role, is_active, changed_by, departments=None,
):
    validate_access_change(username, role, is_active, changed_by)
    if departments is not None:
        normalized = normalize_employee_departments(departments)
        response = supabase.rpc("update_app_user_profile_access", {
            "p_username": str(username).strip(),
            "p_role": str(role).strip(),
            "p_is_active": bool(is_active),
            "p_departments": normalized,
            "p_changed_by": str(changed_by).strip(),
        }).execute()
        return response.data or []
    response = supabase.rpc("update_app_user_access", {
        "p_username": str(username).strip(),
        "p_role": str(role).strip(),
        "p_is_active": bool(is_active),
        "p_changed_by": str(changed_by).strip(),
    }).execute()
    return response.data or []


def load_production_departments(supabase):
    try:
        rows = (
            supabase.table("app_production_departments")
            .select("department_code,department_name,sort_order")
            .eq("is_active", True).order("sort_order").execute().data or []
        )
    except Exception:
        return ["DTF", "UV", "3D"]
    return [str(row["department_code"]).strip() for row in rows]


def normalize_employee_departments(departments):
    allowed = {"DTF", "UV", "3D"}
    result = list(dict.fromkeys(
        str(value or "").strip().upper() for value in departments
        if str(value or "").strip()
    ))
    if not result:
        raise ValueError("员工至少需要选择一个生产部门")
    unsupported = set(result) - allowed
    if unsupported:
        raise ValueError(f"不支持的生产部门：{', '.join(sorted(unsupported))}")
    return result


def create_employee(
    supabase, name, job_title, departments, username="", password="",
    role="visitor",
):
    name = _text(name)
    job_title = _text(job_title)
    username = _text(username)
    if not name or not job_title:
        raise ValueError("姓名和岗位不能为空")
    department_codes = normalize_employee_departments(departments)
    if username:
        if not password:
            raise ValueError("登录账号必须设置密码")
    result = supabase.rpc("register_employee_account", {
        "p_name": name,
        "p_job_title": job_title,
        "p_departments": department_codes,
        "p_username": username or None,
        "p_password": password or None,
        "p_role": role,
    }).execute()
    row = (result.data or [{}])[0]
    return {
        "employee_id": row.get("employee_id", f"{username or name}_id"),
        "departments": row.get("departments", department_codes),
    }


def update_employee_status(
    supabase, employee_id, is_active, effective_date, reason, changed_by,
):
    validate_employee_status_change(
        employee_id, is_active, effective_date, reason, changed_by
    )
    response = supabase.rpc("update_employee_employment_status", {
        "p_employee_id": str(employee_id).strip(),
        "p_is_active": bool(is_active),
        "p_effective_date": effective_date.isoformat(),
        "p_reason": str(reason or "").strip(),
        "p_changed_by": str(changed_by).strip(),
    }).execute()
    return response.data or []


def load_employee_status_audit(supabase, limit=200):
    rows = (
        supabase.table("app_employee_status_audit")
        .select(EMPLOYEE_STATUS_AUDIT_COLUMNS)
        .order("changed_at", desc=True).limit(limit).execute().data
    )
    return pd.DataFrame(rows)


def _load_user_departments(supabase, users):
    employee_ids = users["employee_id"].dropna().astype(str).tolist()
    assignments = {}
    if employee_ids:
        try:
            rows = (
                supabase.table("app_user_departments")
                .select("employee_id,department_code")
                .in_("employee_id", employee_ids).execute().data or []
            )
            for row in rows:
                if not row.get("employee_id") or not row.get("department_code"):
                    continue
                assignments.setdefault(str(row["employee_id"]), []).append(
                    str(row["department_code"])
                )
        except Exception:
            pass
    return users["employee_id"].map(
        lambda value: assignments.get(str(value), ["DTF"])
    )


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


def validate_employee_status_change(
    employee_id, is_active, effective_date, reason, changed_by,
):
    if not str(employee_id or "").strip():
        raise ValueError("请选择员工")
    if effective_date is None:
        raise ValueError("请选择生效日期")
    if not str(changed_by or "").strip():
        raise ValueError("请先登录人员管理员账号")
    if not is_active and not str(reason or "").strip():
        raise ValueError("办理离职时必须填写原因")


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
