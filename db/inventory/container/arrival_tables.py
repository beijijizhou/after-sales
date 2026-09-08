"""Arrival-history sorting and batch summaries for containers."""

import pandas as pd

from db.inventory.container.labels import get_container_display_label


def sort_arrival_history_rows(raw_df, mode="time"):
    if raw_df is None or raw_df.empty:
        return raw_df.copy() if raw_df is not None else pd.DataFrame()

    result = raw_df.copy()
    confirmation_at = pd.to_datetime(
        result.get(
            "arrival_confirmed_at", pd.Series(pd.NaT, index=result.index)
        ),
        errors="coerce",
        utc=True,
    )
    arrival_at = pd.to_datetime(
        result.get("actual_arrival_at", pd.Series(pd.NaT, index=result.index)),
        errors="coerce",
        utc=True,
    )
    arrival_date = pd.to_datetime(
        result.get("actual_arrival_date", pd.Series(pd.NaT, index=result.index)),
        errors="coerce",
        utc=True,
    )
    result["_arrival_sort"] = confirmation_at.fillna(arrival_at).fillna(
        arrival_date
    )
    result["_department_sort"] = result.get(
        "department", pd.Series("", index=result.index)
    ).fillna("").astype(str).str.casefold()
    result["_container_sort"] = result.get(
        "container_no", pd.Series("", index=result.index)
    ).fillna("").astype(str).str.casefold()
    if mode == "department":
        by = ["_department_sort", "_arrival_sort", "_container_sort"]
        ascending = [True, False, True]
    else:
        by = ["_arrival_sort", "_department_sort", "_container_sort"]
        ascending = [False, True, True]
    return result.sort_values(
        by, ascending=ascending, kind="stable", na_position="last"
    ).drop(columns=[
        "_arrival_sort", "_department_sort", "_container_sort",
    ]).reset_index(drop=True)


def build_arrival_batch_summary(raw_df):
    """Collapse arrived container SKU rows into one review row per container."""
    columns = [
        "货柜记录ID", "货柜批次", "实体货柜号", "部门", "品类",
        "实际到柜日期", "确认到柜时间（纽约）", "SKU数", "总件数", "状态",
    ]
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for container_key, group in raw_df.groupby(
        "container_key", sort=False, dropna=False
    ):
        physical_numbers = _nonempty_values(group, "container_no")
        physical_no = physical_numbers[0] if physical_numbers else ""
        arrival_dates = pd.to_datetime(
            group.get("actual_arrival_date"), errors="coerce"
        ).dropna()
        confirmation = pd.to_datetime(
            group.get(
                "arrival_confirmed_at", pd.Series(pd.NaT, index=group.index)
            ),
            errors="coerce",
            utc=True,
        ).dropna()
        confirmation_text = (
            confirmation.max().tz_convert("America/New_York").strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if not confirmation.empty else ""
        )
        identity_columns = [
            column for column in [
                "department", "category", "brand", "material", "color", "size"
            ] if column in group.columns
        ]
        sku_count = (
            group[identity_columns].fillna("").drop_duplicates().shape[0]
            if identity_columns else len(group)
        )
        rows.append({
            "货柜记录ID": container_key,
            "货柜批次": get_container_display_label(
                container_key,
                physical_no,
                group.get("note", pd.Series(dtype=str)).tolist(),
            ),
            "实体货柜号": physical_no,
            "部门": " / ".join(_nonempty_values(group, "department")),
            "品类": " / ".join(_nonempty_values(group, "category")),
            "实际到柜日期": (
                arrival_dates.max().date() if not arrival_dates.empty else None
            ),
            "确认到柜时间（纽约）": confirmation_text,
            "SKU数": int(sku_count),
            "总件数": int(pd.to_numeric(
                group.get("quantity", pd.Series(0, index=group.index)),
                errors="coerce",
            ).fillna(0).sum()),
            "状态": " / ".join(_nonempty_values(group, "status")),
        })
    return pd.DataFrame(rows, columns=columns)


def _nonempty_values(frame, column):
    if column not in frame.columns:
        return []
    return list(dict.fromkeys(
        str(value).strip() for value in frame[column].dropna()
        if str(value).strip()
    ))
