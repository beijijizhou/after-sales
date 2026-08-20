"""Department-specific presentation rules for routine inventory views."""

import pandas as pd


UV_ROUTINE_HIDDEN_COLUMNS = frozenset({"品牌", "颜色"})


def routine_hidden_columns(department):
    """Return identity columns hidden from routine, non-audit views."""
    return (
        UV_ROUTINE_HIDDEN_COLUMNS
        if str(department or "").strip().upper() == "UV"
        else frozenset()
    )


def apply_routine_display_scope(rows, department):
    """Hide presentation-only dimensions without changing stored SKU data."""
    data = pd.DataFrame(rows).copy()
    return data.drop(
        columns=list(routine_hidden_columns(department)), errors="ignore"
    )
