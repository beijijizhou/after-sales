import pandas as pd

from utils.auth.constants import ROLE_ADMIN, ROLE_VISITOR


ALL_DEPARTMENTS = "全部部门"
ALL_JOB_TITLES = "全部岗位"


def employee_creation_error_message(error):
    message = str(error)
    if "users_name_key" in message or (
        "duplicate key" in message and "Key (name)" in message
    ):
        return (
            "该员工姓名已存在，请到“员工名单”中查找，并办理复职或状态调整，"
            "无需重复新增。"
        )
    if "users_user_name_key" in message or (
        "duplicate key" in message and "Key (user_name)" in message
    ):
        return "该登录账号已存在，请更换用户名或在权限管理中检查现有账号。"
    return f"员工创建失败：{message}"


def filter_employees(employees, status):
    if employees.empty or status == "全部":
        return employees.copy()
    active = status == "在职"
    return employees.loc[employees["is_active"] == active].reset_index(drop=True)


def manageable_employees(employees, current_user):
    """Limit people managers to staff below them in their own departments."""
    if employees.empty:
        return employees.copy()
    user = current_user or {}
    if str(user.get("role") or "") == ROLE_ADMIN:
        return employees.copy().reset_index(drop=True)

    managed_departments = {
        str(value or "").strip().upper()
        for value in (user.get("departments") or ["DTF"])
        if str(value or "").strip()
    }
    username = str(user.get("username") or "").strip()
    result = employees.loc[
        employees["role"].fillna(ROLE_VISITOR).eq(ROLE_VISITOR)
    ].copy()
    if username:
        result = result.loc[
            result["user_name"].fillna("").astype(str).str.strip() != username
        ]
    result = result.loc[result["departments"].map(
        lambda values: bool(managed_departments.intersection(
            str(value or "").strip().upper()
            for value in (values or ["DTF"])
            if str(value or "").strip()
        ))
    )]
    return result.reset_index(drop=True)


def filter_employees_by_organization(
    employees, department=ALL_DEPARTMENTS, job_title=ALL_JOB_TITLES,
):
    result = employees.copy()
    if department != ALL_DEPARTMENTS:
        result = result.loc[result["departments"].map(
            lambda values: department in (values or ["DTF"])
        )].copy()
    if job_title != ALL_JOB_TITLES:
        result = result.loc[
            result["job_title"].fillna("员工").astype(str) == job_title
        ].copy()
    return result.reset_index(drop=True)


def employee_department_options(employees):
    values = []
    for departments in employees.get("departments", pd.Series(dtype=object)):
        for department in departments or ["DTF"]:
            if department and department not in values:
                values.append(department)
    return [ALL_DEPARTMENTS, *values]


def employee_job_title_options(employees):
    values = sorted({
        str(value or "员工").strip() or "员工"
        for value in employees.get("job_title", pd.Series(dtype=object))
    })
    return [ALL_JOB_TITLES, *values]


def reset_stale_filter_selection(state, key, options):
    if state.get(key) not in options:
        state.pop(key, None)


def reset_stale_employee_selection(state, key, employee_ids):
    options = {str(value) for value in employee_ids}
    if str(state.get(key) or "") not in options:
        state.pop(key, None)


def employee_table(employees):
    if employees.empty:
        return pd.DataFrame(columns=[
            "姓名", "员工编号", "岗位", "生产部门", "登录账号", "状态",
        ])
    result = employees.copy()
    result["生产部门"] = result["departments"].map(
        lambda values: " / ".join(values or ["DTF"])
    )
    result["登录账号"] = result["user_name"].map(lambda value: value or "—")
    result["状态"] = result["is_active"].map({True: "在职", False: "已离职"})
    return result.rename(columns={
        "name": "姓名", "employee_id": "员工编号", "job_title": "岗位",
    })[["姓名", "员工编号", "岗位", "生产部门", "登录账号", "状态"]]


def employee_label(employee):
    account = f" · {employee['user_name']}" if employee.get("user_name") else ""
    return f"{employee.get('name') or employee['employee_id']}{account}"
