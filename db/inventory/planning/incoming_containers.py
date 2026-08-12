"""Aggregate SKU-level container rows into chronological arrival plans."""

from datetime import timedelta

import pandas as pd

from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    normalize_container_state,
)
from utils.erp.inventory_mapping import KEY_COLUMNS


def all_incoming(df, today):
    columns = [
        *KEY_COLUMNS, "first_arrival_date", "last_arrival_date",
        "incoming_quantity", "container_no", "normalized_status",
        "arrival_schedule", "arrival_overview", "arrival_events",
        "has_overdue_estimate",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    result = df.copy()
    result["quantity"] = pd.to_numeric(
        result["quantity"], errors="coerce"
    ).fillna(0)
    for column in ["expected_arrival_date", "actual_arrival_date"]:
        result[column] = pd.to_datetime(
            result.get(column), errors="coerce"
        ).dt.date
    result["normalized_status"] = result.get(
        "status", ""
    ).map(normalize_container_state)
    arrived = result["normalized_status"] == STATE_ARRIVED
    result["forecast_arrival_date"] = result["expected_arrival_date"]
    result.loc[arrived, "forecast_arrival_date"] = result.loc[arrived].apply(
        lambda row: row["actual_arrival_date"]
        if pd.notna(row["actual_arrival_date"])
        else row["expected_arrival_date"], axis=1,
    )
    result["original_forecast_arrival_date"] = result["forecast_arrival_date"]
    result["overdue_estimate"] = (
        ~arrived & result["forecast_arrival_date"].notna()
        & (result["forecast_arrival_date"] < today)
    )
    result.loc[result["overdue_estimate"], "forecast_arrival_date"] = (
        today + timedelta(days=1)
    )
    result = result.dropna(subset=["forecast_arrival_date"])
    result["container_no"] = result["container_no"].fillna(
        result["container_key"]
    ).astype(str)
    rows = []
    for identity, group in result.groupby(KEY_COLUMNS, dropna=False):
        schedule = group.groupby(
            [
                "forecast_arrival_date", "container_no", "normalized_status",
                "original_forecast_arrival_date", "overdue_estimate",
            ], dropna=False, as_index=False,
        )["quantity"].sum().sort_values(
            ["forecast_arrival_date", "container_no"]
        )
        events = [
            (row["forecast_arrival_date"], float(row["quantity"]))
            for row in schedule.to_dict("records")
        ]
        schedule_text = "｜".join(
            f"{row['forecast_arrival_date']:%m/%d} {row['container_no']} "
            f"{int(row['quantity']):,}"
            + (
                f"（原预计{row['original_forecast_arrival_date']:%m/%d}，"
                "延期按明日估算）" if row["overdue_estimate"] else ""
            )
            for row in schedule.to_dict("records")
        )
        daily = schedule.groupby(
            "forecast_arrival_date", as_index=False
        ).agg(
            quantity=("quantity", "sum"),
            containers=("container_no", "nunique"),
            overdue_estimate=("overdue_estimate", "max"),
        ).sort_values("forecast_arrival_date")
        overview = "｜".join(
            f"{row['forecast_arrival_date']:%m/%d} "
            + (
                f"{int(row['containers'])}柜共到货 "
                if int(row["containers"]) > 1 else "到货 "
            )
            + f"{int(row['quantity']):,}片"
            + ("（延期按明日估算）" if row["overdue_estimate"] else "")
            for row in daily.to_dict("records")
        )
        rows.append({
            **dict(zip(KEY_COLUMNS, identity)),
            "first_arrival_date": schedule["forecast_arrival_date"].min(),
            "last_arrival_date": schedule["forecast_arrival_date"].max(),
            "incoming_quantity": float(schedule["quantity"].sum()),
            "container_no": join_unique(schedule["container_no"]),
            "normalized_status": join_unique(schedule["normalized_status"]),
            "arrival_schedule": schedule_text, "arrival_overview": overview,
            "arrival_events": events,
            "has_overdue_estimate": bool(schedule["overdue_estimate"].any()),
        })
    return pd.DataFrame(rows, columns=columns)


def join_unique(values):
    return " / ".join(sorted({
        str(value).strip() for value in values if str(value).strip()
    }))
