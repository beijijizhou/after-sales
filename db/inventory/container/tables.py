from datetime import date

import pandas as pd

from db.inventory.container.labels import get_container_display_label

from db.inventory import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT, SIZE_COLUMNS
from db.inventory.container.model_tables import (
    build_model_container_display,
    uses_model_rows,
)
from db.inventory.container.summary_tables import (
    build_container_inventory_summary,
    build_filtered_container_summary,
    container_display_columns,
    get_container_item_columns,
    ordered_item_columns as _ordered_item_columns,
)
from db.inventory.container.input_tables import (
    CONTAINER_STATUSES,
    DEFAULT_TRANSIT_DAYS,
    add_optional_columns,
    build_container_schedule_preview,
    build_container_template,
    normalize_container_rows,
)


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
        result.get(
            "actual_arrival_at", pd.Series(pd.NaT, index=result.index)
        ),
        errors="coerce",
        utc=True,
    )
    arrival_date = pd.to_datetime(
        result.get(
            "actual_arrival_date", pd.Series(pd.NaT, index=result.index)
        ),
        errors="coerce",
        utc=True,
    )
    result["_arrival_sort"] = confirmation_at.fillna(
        arrival_at
    ).fillna(arrival_date)
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
            errors="coerce", utc=True,
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
                container_key, physical_no,
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


def build_container_display(df, include_cost=False):
    if uses_model_rows(df):
        return build_model_container_display(df, include_cost)
    item_columns = _ordered_item_columns(df.get("size", []))
    columns = container_display_columns(include_cost, item_columns)
    if df.empty:
        return pd.DataFrame(columns=columns)

    display = df.copy()
    for column in ["shipped_date", "expected_arrival_date", "actual_arrival_date"]:
        display[column] = pd.to_datetime(display[column], errors="coerce").dt.date
    display["actual_arrival_at"] = _format_ny_datetime(
        display.get("actual_arrival_at")
    )
    display["arrival_confirmed_at"] = _format_ny_datetime(
        display.get("arrival_confirmed_at")
    )
    missing_arrival = date(1900, 1, 1)
    display["actual_arrival_date"] = display["actual_arrival_date"].fillna(
        missing_arrival
    )
    for column in ["container_no", "category", "brand", "material", "note"]:
        display[column] = display[column].fillna("")
    display["department"] = display["department"].fillna(DEFAULT_DEPARTMENT)
    index = [
        "container_key", "shipped_date", "expected_arrival_date",
        "actual_arrival_date", "actual_arrival_at",
        "arrival_confirmed_at",
        "container_no", "department",
        "category", "brand", "material", "color",
        *(["unit_cost"] if include_cost else []), "status", "note",
    ]
    pivot = display.pivot_table(
        index=index, columns="size", values="quantity", aggfunc="sum", fill_value=0
    ).reset_index()
    for item in item_columns:
        if item not in pivot.columns:
            pivot[item] = 0
        pivot[item] = pd.to_numeric(
            pivot[item], errors="coerce"
        ).fillna(0).astype(int)
    pivot["总件数"] = pivot[item_columns].sum(axis=1)
    pivot.loc[
        pivot["actual_arrival_date"] == missing_arrival, "actual_arrival_date"
    ] = None
    pivot["运输天数"] = pivot.apply(
        lambda row: (row["expected_arrival_date"] - row["shipped_date"]).days,
        axis=1,
    )
    pivot = pivot.rename(columns={
        "shipped_date": "发货日期", "expected_arrival_date": "预计到货日期",
        "actual_arrival_date": "实际到货日期", "container_key": "货柜记录ID",
        "actual_arrival_at": "实际到货时间（纽约）",
        "arrival_confirmed_at": "确认到柜时间（纽约）",
        "container_no": "货柜号", "department": "部门", "category": "品类",
        "brand": "品牌", "material": "材质", "color": "颜色",
        "unit_cost": "成本", "status": "状态", "note": "备注",
    })
    pivot["批次标识"] = pivot.apply(
        lambda row: get_container_display_label(
            row["货柜记录ID"], row["货柜号"], [row.get("备注", "")]
        ),
        axis=1,
    )
    return pivot[columns]


def _format_ny_datetime(values):
    if values is None:
        return ""
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_convert("America/New_York").dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    ).fillna("")
