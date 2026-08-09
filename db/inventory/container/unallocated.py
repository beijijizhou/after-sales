import re

import pandas as pd

from db.inventory.container.labels import get_container_display_label


_CUP_CASE_PATTERN = re.compile(r"保温杯\s*(?P<cases>[\d,]+)\s*(?:件|箱)")


def build_unallocated_cup_cargo(container_df):
    columns = ["货柜", "预计到货", "箱数", "状态"]
    if container_df is None or container_df.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for container_key, group in container_df.groupby("container_key", sort=False):
        notes = list(dict.fromkeys(
            str(value or "").strip()
            for value in group.get("note", pd.Series(dtype=str)).tolist()
            if str(value or "").strip()
        ))
        quantities = {
            int(match.group("cases").replace(",", ""))
            for note in notes
            for match in _CUP_CASE_PATTERN.finditer(note)
        }
        if not quantities:
            continue
        first = group.iloc[0]
        expected = pd.to_datetime(
            first.get("expected_arrival_date"), errors="coerce"
        )
        rows.append({
            "货柜": get_container_display_label(
                container_key, first.get("container_no"), notes
            ),
            "预计到货": None if pd.isna(expected) else expected.date(),
            "箱数": max(quantities),
            "状态": str(first.get("status") or ""),
        })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["预计到货", "货柜"], na_position="last", kind="stable"
    ).reset_index(drop=True)


def attach_unallocated_cup_cargo(forecast_df, cargo_df):
    """Show shared cup cargo without inventing an SKU-level allocation."""
    result = forecast_df.copy()
    for column in [
        "待确认在途货柜", "待确认到货安排", "待确认到货概览",
    ]:
        if column not in result.columns:
            result[column] = ""
    if result.empty or cargo_df is None or cargo_df.empty:
        return result
    schedules = []
    for row in cargo_df.to_dict("records"):
        date_label = (
            row["预计到货"].strftime("%m/%d")
            if hasattr(row["预计到货"], "strftime") else "日期待定"
        )
        schedules.append(
            f"{date_label} {row['货柜']} {int(row['箱数']):,}箱"
        )
    cup_rows = result["品类"].astype(str).str.strip().eq("保温杯")
    result.loc[cup_rows, "待确认在途货柜"] = "、".join(
        cargo_df["货柜"].tolist()
    )
    result.loc[cup_rows, "待确认到货安排"] = (
        "｜".join(schedules) + "（直杯/咖啡杯箱数分配待确认）"
    )
    result.loc[cup_rows, "待确认到货概览"] = "｜".join(
        (
            f"{row['预计到货']:%m/%d} 到货 {int(row['箱数']):,}箱"
            if hasattr(row["预计到货"], "strftime")
            else f"日期待定 到货 {int(row['箱数']):,}箱"
        )
        for row in cargo_df.to_dict("records")
    ) + "（直杯/咖啡杯分配待确认）"
    return result
