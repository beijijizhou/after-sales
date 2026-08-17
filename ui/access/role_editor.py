import pandas as pd
import streamlit as st

from db.access import save_role_definition, validate_role_definition
from ui.access.permissions import (
    role_labels,
    role_permission_map,
)
from utils.auth import get_current_user


def render_role_configuration(supabase, roles, catalog, assigned):
    st.info(
        "创建或修改角色时可自由组合现有权限。保存前请核对逐项变化；"
        "保存后会记录操作人、时间以及修改前后完整快照。"
    )
    mode = st.radio(
        "配置方式", ("编辑现有角色", "创建新角色"),
        horizontal=True, key="access_role_configuration_mode",
    )
    labels = role_labels(roles)
    assigned_map = role_permission_map(assigned)
    permission_options = catalog["permission_key"].astype(str).tolist()
    permission_display = {
        str(row["permission_key"]): (
            f"{row['permission_group']} · {row['permission_name']}"
        )
        for row in catalog.to_dict("records")
    }

    if mode == "编辑现有角色":
        role_options = roles["role_key"].astype(str).tolist()
        selected_key = st.selectbox(
            "选择角色", role_options,
            format_func=lambda key: labels.get(str(key), str(key)),
            key="access_role_configuration_target",
        )
        selected = roles.loc[roles["role_key"] == selected_key].iloc[0]
        default_name = str(selected["role_name"])
        default_description = str(selected.get("description") or "")
        default_permissions = sorted(assigned_map.get(selected_key, set()))
        role_key_disabled = True
    else:
        selected_key = ""
        default_name = ""
        default_description = ""
        default_permissions = []
        role_key_disabled = False

    scope = selected_key or "new"
    with st.form(f"access_role_configuration_form_{scope}"):
        role_key = st.text_input(
            "角色标识",
            value=selected_key,
            disabled=role_key_disabled,
            help="创建后不可修改；使用3–32位小写字母、数字或下划线。",
        )
        role_name = st.text_input("角色名称", value=default_name)
        description = st.text_area("角色说明", value=default_description)
        selected_permissions = st.multiselect(
            "权限组合", permission_options,
            default=default_permissions,
            format_func=lambda key: permission_display.get(str(key), str(key)),
        )
        preview = role_permission_preview(
            catalog, default_permissions, selected_permissions
        )
        st.caption("权限变化预览")
        st.dataframe(preview, hide_index=True, width="stretch")
        confirmed = st.checkbox("我已核对角色信息和全部权限变化")
        changed = (
            mode == "创建新角色"
            or role_name.strip() != default_name
            or description.strip() != default_description
            or set(selected_permissions) != set(default_permissions)
        )
        submitted = st.form_submit_button(
            "保存角色配置", type="primary", width="stretch",
            disabled=not confirmed or not changed,
        )
    if not submitted:
        return

    actor = str((get_current_user() or {}).get("username") or "").strip()
    try:
        validate_role_definition(role_key, role_name, selected_permissions)
        save_role_definition(
            supabase, role_key, role_name, description,
            selected_permissions, actor,
        )
    except Exception as error:
        st.error(_role_error_message(error))
        return
    st.session_state["access_management_notice"] = (
        f"已保存角色 {role_name.strip()}，包含 {len(selected_permissions):,} 项权限。"
    )
    st.rerun()


def role_permission_preview(catalog, old_permissions, new_permissions):
    old_permissions = set(old_permissions)
    new_permissions = set(new_permissions)
    rows = []
    for item in catalog.sort_values("sort_order").to_dict("records"):
        key = str(item["permission_key"])
        if key in old_permissions and key in new_permissions:
            change = "保留"
        elif key in new_permissions:
            change = "新增"
        elif key in old_permissions:
            change = "移除"
        else:
            change = "未启用"
        rows.append({
            "权限分组": item["permission_group"],
            "权限": item["permission_name"],
            "权限标识": key,
            "修改前": "✓" if key in old_permissions else "",
            "修改后": "✓" if key in new_permissions else "",
            "变化": change,
        })
    return pd.DataFrame(rows)


def _role_error_message(error):
    message = str(error)
    if "upsert_app_role" in message:
        return (
            "动态角色数据库尚未安装，请按顺序执行 "
            "sql/access/role_management/ 下的 01–11 脚本。"
        )
    return message
