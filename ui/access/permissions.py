import pandas as pd
import streamlit as st


def role_labels(roles):
    if roles.empty:
        return {}
    return dict(zip(
        roles["role_key"].astype(str),
        roles["role_name"].astype(str),
    ))


def role_permission_map(role_permissions):
    if role_permissions.empty:
        return {}
    return {
        str(role): set(group["permission_key"].astype(str))
        for role, group in role_permissions.groupby("role_key")
    }


def permission_labels(catalog):
    if catalog.empty:
        return {}
    return dict(zip(
        catalog["permission_key"].astype(str),
        catalog["permission_name"].astype(str),
    ))


def permission_names(permissions, catalog):
    labels = permission_labels(catalog)
    return "、".join(labels.get(item, item) for item in permissions)


def permission_matrix(roles, catalog, role_permissions):
    labels = role_labels(roles)
    assigned = role_permission_map(role_permissions)
    ordered_permissions = (
        catalog.sort_values("sort_order")[
            ["permission_key", "permission_name"]
        ].to_dict("records")
        if not catalog.empty else []
    )
    rows = []
    for role in roles.to_dict("records"):
        role_key = str(role["role_key"])
        rows.append({
            "角色": labels.get(role_key, role_key),
            **{
                str(permission["permission_name"]): (
                    "✓"
                    if str(permission["permission_key"])
                    in assigned.get(role_key, set()) else ""
                )
                for permission in ordered_permissions
            },
        })
    return pd.DataFrame(rows)


def role_permission_summary(roles, catalog, role_permissions):
    labels = role_labels(roles)
    assigned = role_permission_map(role_permissions)
    total = len(catalog)
    rows = []
    for role in roles.to_dict("records"):
        key = str(role["role_key"])
        count = len(assigned.get(key, set()))
        rows.append({
            "角色": labels.get(key, key),
            "角色标识": key,
            "已启用权限": count,
            "全部权限": total,
            "覆盖率": round(count * 100 / total) if total else 0,
            "角色说明": str(role.get("description") or ""),
        })
    return pd.DataFrame(rows)


def role_permission_detail(role_key, catalog, role_permissions, group=None):
    assigned = role_permission_map(role_permissions).get(str(role_key), set())
    source = catalog.sort_values("sort_order")
    if group:
        source = source[source["permission_group"] == group]
    return pd.DataFrame([{
        "权限分组": row["permission_group"],
        "权限": row["permission_name"],
        "状态": "✓ 已启用" if str(row["permission_key"]) in assigned else "— 未启用",
        "权限标识": row["permission_key"],
        "说明": row.get("description") or "",
    } for row in source.to_dict("records")])


def permission_group_matrix(group, roles, catalog, role_permissions):
    group_catalog = catalog[catalog["permission_group"] == group]
    return permission_matrix(roles, group_catalog, role_permissions)


def render_permission_overview(roles, catalog, role_permissions):
    st.info(
        "先选择角色查看分组明细，或选择权限组横向比较角色。"
        "完整矩阵保留在页面底部。"
    )
    summary = role_permission_summary(roles, catalog, role_permissions)
    metrics = st.columns(3)
    metrics[0].metric("角色数量", f"{len(roles):,}")
    metrics[1].metric("权限数量", f"{len(catalog):,}")
    metrics[2].metric("已分配关系", f"{len(role_permissions):,}")
    st.markdown("#### 角色摘要")
    st.dataframe(
        summary, hide_index=True, width="stretch",
        column_config={
            "覆盖率": st.column_config.ProgressColumn(
                "权限覆盖率", min_value=0, max_value=100, format="%d%%"
            ),
            "角色说明": st.column_config.TextColumn("角色说明", width="large"),
        },
    )

    view = st.segmented_control(
        "查看方式", ["按角色查看", "按权限组对比"],
        default="按角色查看", key="access_permission_view_mode",
    )
    if view == "按权限组对比":
        _render_group_comparison(roles, catalog, role_permissions)
    else:
        _render_role_detail(roles, catalog, role_permissions)

    with st.expander("完整权限矩阵（高级核查）", expanded=False):
        matrix = permission_matrix(roles, catalog, role_permissions)
        st.caption("权限较多时需要横向滚动；日常查看建议使用上方分组视图。")
        st.dataframe(matrix, hide_index=True, width="stretch")
        st.download_button(
            "下载完整权限矩阵 CSV",
            matrix.to_csv(index=False).encode("utf-8-sig"),
            file_name="角色权限矩阵.csv", mime="text/csv",
            width="stretch",
        )


def _render_role_detail(roles, catalog, role_permissions):
    labels = role_labels(roles)
    role_options = roles["role_key"].astype(str).tolist()
    selected_role = st.selectbox(
        "选择角色", role_options,
        format_func=lambda key: labels.get(key, key),
        key="access_permission_role_detail",
    )
    groups = catalog.sort_values("sort_order")["permission_group"].drop_duplicates().tolist()
    selected_group = st.selectbox(
        "权限分组", ["全部分组", *groups],
        key="access_permission_role_group",
    )
    detail = role_permission_detail(
        selected_role, catalog, role_permissions,
        None if selected_group == "全部分组" else selected_group,
    )
    enabled = int(detail["状态"].str.startswith("✓").sum()) if not detail.empty else 0
    st.caption(f"当前范围已启用 {enabled:,} / {len(detail):,} 项权限")
    st.dataframe(detail, hide_index=True, width="stretch")


def _render_group_comparison(roles, catalog, role_permissions):
    groups = catalog.sort_values("sort_order")["permission_group"].drop_duplicates().tolist()
    if not groups:
        st.info("当前没有权限分组。")
        return
    selected_group = st.selectbox(
        "选择权限分组", groups, key="access_permission_compare_group"
    )
    st.dataframe(
        permission_group_matrix(
            selected_group, roles, catalog, role_permissions
        ),
        hide_index=True, width="stretch",
    )
