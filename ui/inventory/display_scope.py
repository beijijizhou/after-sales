"""Department-specific presentation rules for routine inventory views."""

import pandas as pd


UV_ROUTINE_HIDDEN_COLUMNS = frozenset({"品牌", "颜色"})


def routine_hidden_columns(department, rows=None, hierarchy_fields=None):
    """Hide UV color only when it does not distinguish visible SKUs."""
    if str(department or "").strip().upper() != "UV":
        return frozenset()
    if "color" in tuple(hierarchy_fields or ()):
        return frozenset({"品牌"})
    data = pd.DataFrame(rows) if rows is not None else pd.DataFrame()
    color_column = next(
        (column for column in ("颜色", "color") if column in data), None
    )
    if color_column is None or data.empty:
        return UV_ROUTINE_HIDDEN_COLUMNS
    category_column = next(
        (column for column in ("品类", "category") if column in data), None
    )
    material_column = next(
        (column for column in ("材质", "material") if column in data), None
    )
    model_column = next(
        (column for column in ("型号", "尺码", "size") if column in data), None
    )
    identity = [
        column for column in (category_column, material_column, model_column)
        if column is not None
    ]
    if not identity:
        return UV_ROUTINE_HIDDEN_COLUMNS
    colors = data.assign(
        _visible_color=data[color_column].fillna("").astype(str).str.strip()
    )
    distinct_colors = colors.groupby(identity, dropna=False)[
        "_visible_color"
    ].nunique()
    if distinct_colors.gt(1).any():
        return frozenset({"品牌"})
    return UV_ROUTINE_HIDDEN_COLUMNS


def apply_routine_display_scope(rows, department):
    """Hide presentation-only dimensions without changing stored SKU data."""
    data = pd.DataFrame(rows).copy()
    return data.drop(
        columns=list(routine_hidden_columns(department, data)), errors="ignore"
    )
