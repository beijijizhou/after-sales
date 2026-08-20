import pandas as pd


def filter_employees(employees, status):
    if employees.empty or status == "全部":
        return employees.copy()
    active = status == "在职"
    return employees.loc[employees["is_active"] == active].reset_index(drop=True)


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
