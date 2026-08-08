import pandas as pd


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
