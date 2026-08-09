import pandas as pd

from db.inventory.container.labels import (
    get_container_business_name,
    get_container_display_label,
)


def build_container_progress_choices(progress_df):
    if progress_df is None or progress_df.empty:
        return {}
    choices = {}
    for row in progress_df.to_dict("records"):
        container_key = str(row.get("货柜记录ID") or "").strip()
        if not container_key:
            continue
        container_no = str(row.get("货柜号") or "").strip()
        business_name = str(
            row.get("货柜备注")
            or get_container_business_name(container_key, container_no)
        ).strip()
        expected = row.get("预计到货日期")
        date_label = (
            expected.strftime("%m/%d")
            if hasattr(expected, "strftime") else str(expected or "未定")
        )
        quantity = int(row.get("总件数") or 0)
        alert = str(row.get("到货提醒") or "").strip()
        label = get_container_display_label(
            container_key, container_no, business_name=business_name
        )
        label = f"{label}｜到货 {date_label}｜{quantity:,} 件"
        if alert:
            label += f"｜{alert}"
        choices[container_key] = label
    return choices


def build_container_progress_summary(df, today):
    columns = [
        "货柜记录ID", "货柜备注", "货柜号", "部门", "品类", "发货日期", "预计到货日期",
        "已运输天数", "剩余天数", "到货提醒", "运输进度", "总件数", "状态",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    data = df.copy()
    data["shipped_date"] = pd.to_datetime(
        data["shipped_date"], errors="coerce"
    ).dt.date
    data["expected_arrival_date"] = pd.to_datetime(
        data["expected_arrival_date"], errors="coerce"
    ).dt.date
    rows = []
    for container_key, group in data.groupby("container_key", sort=False):
        shipped_date = group["shipped_date"].min()
        expected_date = group["expected_arrival_date"].max()
        transit_days = max((expected_date - shipped_date).days, 1)
        elapsed_days = max((today - shipped_date).days, 0)
        remaining_days = (expected_date - today).days
        progress = min(round(elapsed_days / transit_days * 100), 100)
        if remaining_days < 0:
            arrival_alert = f"已延迟 {abs(remaining_days)} 天"
        elif remaining_days <= 7:
            arrival_alert = (
                "预计今天到货"
                if remaining_days == 0
                else f"{remaining_days} 天内到货"
            )
        else:
            arrival_alert = ""
        departments = sorted({
            str(value).strip() for value in group["department"].dropna()
            if str(value).strip()
        })
        categories = sorted({
            str(value).strip() for value in group["category"].dropna()
            if str(value).strip()
        })
        container_no = group["container_no"].dropna().astype(str).str.strip()
        physical_no = container_no.iloc[0] if not container_no.empty else ""
        notes = group.get("note", pd.Series(dtype=str)).tolist()
        rows.append({
            "货柜记录ID": container_key,
            "货柜备注": get_container_business_name(
                container_key, physical_no, notes
            ),
            "货柜号": physical_no,
            "部门": " / ".join(departments),
            "品类": " / ".join(categories),
            "发货日期": shipped_date,
            "预计到货日期": expected_date,
            "已运输天数": elapsed_days,
            "剩余天数": remaining_days,
            "到货提醒": arrival_alert,
            "运输进度": progress,
            "总件数": int(pd.to_numeric(
                group["quantity"], errors="coerce"
            ).fillna(0).sum()),
            "状态": group["status"].iloc[0],
        })
    result = pd.DataFrame(rows, columns=columns)
    result["_alert_order"] = result["剩余天数"].map(
        lambda value: 0 if value < 0 else (1 if value <= 7 else 2)
    )
    return result.sort_values(
        ["_alert_order", "预计到货日期"], ascending=[True, True]
    ).drop(columns="_alert_order").reset_index(drop=True)
