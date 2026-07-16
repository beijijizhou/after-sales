import pandas as pd


def build_container_progress_summary(df, today):
    columns = [
        "货柜记录ID", "货柜号", "部门", "品类", "发货日期", "预计到货日期",
        "已运输天数", "剩余天数", "运输进度", "总件数", "状态",
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
        departments = sorted({
            str(value).strip() for value in group["department"].dropna()
            if str(value).strip()
        })
        categories = sorted({
            str(value).strip() for value in group["category"].dropna()
            if str(value).strip()
        })
        container_no = group["container_no"].dropna().astype(str).str.strip()
        rows.append({
            "货柜记录ID": container_key,
            "货柜号": container_no.iloc[0] if not container_no.empty else container_key,
            "部门": " / ".join(departments),
            "品类": " / ".join(categories),
            "发货日期": shipped_date,
            "预计到货日期": expected_date,
            "已运输天数": elapsed_days,
            "剩余天数": remaining_days,
            "运输进度": progress,
            "总件数": int(pd.to_numeric(
                group["quantity"], errors="coerce"
            ).fillna(0).sum()),
            "状态": group["status"].iloc[0],
        })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["运输进度", "预计到货日期"], ascending=[False, True]
    ).reset_index(drop=True)
