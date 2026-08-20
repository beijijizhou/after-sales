import pandas as pd
import streamlit as st

from db.access import (
    load_production_departments,
    update_user_access,
    validate_access_change,
)
from ui.access.permissions import (
    permission_names,
    role_labels,
    role_permission_map,
)
from utils.auth import get_current_user


def render_user_role_editor(supabase, users, roles, catalog, assigned):
    labels = role_labels(roles)
    permissions_by_role = role_permission_map(assigned)
    active_count = int(users["is_active"].sum()) if not users.empty else 0
    if users.empty:
        st.info("当前没有可管理的登录账号。")
        return

    summary_roles = ("visitor", "producer", "supervisor", "after_sales")
    metrics = st.columns(len(summary_roles))
    for column, role in zip(metrics, summary_roles):
        column.metric(labels.get(role, role), int((users["role"] == role).sum()))
    st.caption(f"全部登录账号 {len(users):,}｜启用 {active_count:,}")

    role_options = roles["role_key"].astype(str).tolist()
    department_options = load_production_departments(supabase)
    filter_columns = st.columns([3, 2])
    selected_roles = filter_columns[0].multiselect(
        "角色筛选", role_options, default=role_options,
        format_func=lambda role: labels.get(str(role), str(role)),
        key="access_management_role_filter",
    )
    selected_status = filter_columns[1].selectbox(
        "账号状态", ("全部", "启用", "停用"),
        key="access_management_status_filter",
    )
    filtered = filter_access_users(users, selected_roles, selected_status)
    st.dataframe(
        user_access_table(filtered, labels), hide_index=True, width="stretch",
    )
    st.caption(f"当前筛选显示 {len(filtered):,} 个登录账号。")
    if filtered.empty:
        st.info("当前筛选条件下没有用户，请调整角色或账号状态。")
        return

    options = [str(value) for value in filtered["user_name"].tolist()]
    user_labels = {
        str(row["user_name"]): (
            f"{row.get('name') or row['user_name']} · {row['user_name']}"
        )
        for row in filtered.to_dict("records")
    }
    scope_key = "_".join(selected_roles) + f"_{selected_status}"
    selected_username = st.selectbox(
        "选择用户", options,
        format_func=lambda value: str(user_labels.get(str(value)) or value),
        key=f"access_management_user_{scope_key}",
    )
    selected = filtered.loc[
        filtered["user_name"].astype(str) == selected_username
    ].iloc[0].to_dict()
    role_index = role_options.index(selected["role"])
    with st.form(f"access_role_form_{selected_username}"):
        new_role = st.selectbox(
            "角色", role_options, index=role_index,
            format_func=lambda role: labels.get(str(role), str(role)),
            key=f"access_role_value_{selected_username}",
        )
        current_departments = list(selected.get("departments") or ["DTF"])
        new_departments = st.multiselect(
            "生产部门（可多选）",
            department_options,
            default=[
                value for value in current_departments
                if value in department_options
            ] or ["DTF"],
            key=f"access_departments_value_{selected_username}",
        )
        new_active = st.checkbox(
            "账号启用", value=bool(selected["is_active"]),
            key=f"access_active_value_{selected_username}",
        )
        preview = access_change_preview(
            selected, new_role, new_active, labels,
            permissions_by_role, catalog, new_departments,
        )
        st.caption("修改预览")
        st.dataframe(pd.DataFrame([preview]), hide_index=True, width="stretch")
        confirmed = st.checkbox("我已核对用户、角色和权限变化")
        submitted = st.form_submit_button(
            "保存权限变更", type="primary", width="stretch",
            disabled=not confirmed or not preview["是否变化"],
        )
    if not submitted:
        return

    actor = str((get_current_user() or {}).get("username") or "").strip()
    try:
        validate_access_change(selected_username, new_role, new_active, actor)
        update_user_access(
            supabase, selected_username, new_role, new_active, actor,
            departments=new_departments,
        )
    except Exception as error:
        st.error(_access_error_message(error))
        return
    st.session_state["access_management_notice"] = (
        f"已更新 {user_labels[selected_username]}："
        f"{labels.get(new_role, new_role)} / {'启用' if new_active else '停用'}"
    )
    st.rerun()


def user_access_table(users, labels=None):
    labels = labels or {}
    if users.empty:
        return pd.DataFrame(
            columns=["姓名", "账号", "员工编号", "岗位", "生产部门", "角色", "状态"]
        )
    result = users.rename(columns={
        "name": "姓名", "user_name": "账号", "employee_id": "员工编号",
        "job_title": "岗位", "role": "角色", "is_active": "状态",
    }).copy()
    result["生产部门"] = result["departments"].map(
        lambda values: " / ".join(values or ["DTF"])
    )
    result["角色"] = result["角色"].map(
        lambda role: labels.get(str(role), str(role))
    )
    result["状态"] = result["状态"].map({True: "启用", False: "停用"})
    return result[
        ["姓名", "账号", "员工编号", "岗位", "生产部门", "角色", "状态"]
    ]


def filter_access_users(users, selected_roles, selected_status):
    if users.empty or not selected_roles:
        return users.iloc[0:0].copy()
    result = users.loc[users["role"].isin(selected_roles)].copy()
    if selected_status != "全部":
        result = result.loc[
            result["is_active"] == (selected_status == "启用")
        ].copy()
    role_order = {role: index for index, role in enumerate(selected_roles)}
    result["_role_order"] = result["role"].map(role_order)
    return (
        result.sort_values(["_role_order", "name", "user_name"])
        .drop(columns="_role_order").reset_index(drop=True)
    )


def access_change_preview(
    user, new_role, new_active, labels=None,
    permissions_by_role=None, catalog=None, new_departments=None,
):
    labels = labels or {}
    permissions_by_role = permissions_by_role or {}
    catalog = catalog if catalog is not None else pd.DataFrame()
    old_role = str(user.get("role") or "visitor")
    old_permissions = permissions_by_role.get(old_role, set())
    new_permissions = permissions_by_role.get(new_role, set())
    added = sorted(new_permissions - old_permissions)
    removed = sorted(old_permissions - new_permissions)
    old_departments = list(user.get("departments") or ["DTF"])
    target_departments = list(new_departments or old_departments)
    return {
        "账号": str(user.get("user_name") or ""),
        "原角色": labels.get(old_role, old_role),
        "新角色": labels.get(new_role, new_role),
        "原状态": "启用" if user.get("is_active") else "停用",
        "新状态": "启用" if new_active else "停用",
        "新增权限": permission_names(added, catalog) or "无",
        "移除权限": permission_names(removed, catalog) or "无",
        "原生产部门": " / ".join(old_departments),
        "新生产部门": " / ".join(target_departments),
        "是否变化": (
            old_role != new_role
            or bool(user.get("is_active")) != new_active
            or set(old_departments) != set(target_departments)
        ),
    }


def _access_error_message(error):
    message = str(error)
    if "update_app_user_access" in message:
        return (
            "动态角色数据库尚未安装，请按顺序执行 "
            "sql/access/role_management/ 下的 01–12 脚本。"
        )
    return message
