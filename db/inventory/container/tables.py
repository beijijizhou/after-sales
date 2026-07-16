from datetime import date, timedelta
from uuid import uuid4

import pandas as pd

from db.inventory import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT, SIZE_COLUMNS


CONTAINER_STATUSES = ["未到货", "已到货", "延迟", "取消"]
DEFAULT_TRANSIT_DAYS = 45


def build_container_template(today=None):
    shipped_date = today or date.today()
    return pd.DataFrame([{
        "发货日期": shipped_date,
        "预计运输天数": DEFAULT_TRANSIT_DAYS,
        "货柜号": "",
        "部门": DEFAULT_DEPARTMENT,
        "品类": DEFAULT_CATEGORY,
        "品牌": "",
        "材质": "180g",
        "颜色": "",
        "成本": 0,
        **{size: 0 for size in SIZE_COLUMNS},
        "状态": "未到货",
        "备注": "",
    }])


def normalize_container_rows(df):
    required = {"发货日期", "预计运输天数", "部门", "材质", "颜色", *SIZE_COLUMNS}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"缺少列：{', '.join(sorted(missing))}")

    result = add_optional_columns(df.copy())
    result["发货日期"] = pd.to_datetime(result["发货日期"], errors="coerce").dt.date
    result["预计运输天数"] = pd.to_numeric(
        result["预计运输天数"], errors="coerce"
    ).fillna(DEFAULT_TRANSIT_DAYS).clip(lower=1).astype(int)
    result["预计到货日期"] = result.apply(
        lambda row: row["发货日期"] + timedelta(days=int(row["预计运输天数"]))
        if pd.notna(row["发货日期"]) else None,
        axis=1,
    )
    for column, default in [
        ("货柜号", ""), ("部门", DEFAULT_DEPARTMENT), ("品类", ""),
        ("品牌", ""), ("材质", "180g"), ("颜色", ""),
        ("状态", "未到货"), ("备注", ""),
    ]:
        result[column] = result[column].fillna(default).astype(str).str.strip()
    container_keys = {}

    def get_container_key(row):
        normalized_no = "".join(row["货柜号"].upper().split())
        if normalized_no:
            return container_keys.setdefault(normalized_no, normalized_no)
        return str(uuid4())

    result["货柜记录ID"] = result.apply(get_container_key, axis=1)
    result["成本"] = pd.to_numeric(result["成本"], errors="coerce").fillna(0)
    result.loc[~result["状态"].isin(CONTAINER_STATUSES), "状态"] = "未到货"
    for size in SIZE_COLUMNS:
        result[size] = pd.to_numeric(result[size], errors="coerce").fillna(0).astype(int)

    result = result.dropna(subset=["发货日期", "预计到货日期"])
    result = result[(result["部门"] != "") & (result["材质"] != "") & (result["颜色"] != "")]
    details = result.melt(
        id_vars=[
            "货柜记录ID", "发货日期", "预计运输天数", "预计到货日期", "货柜号", "部门",
            "品类", "品牌", "材质", "颜色", "成本", "状态", "备注",
        ],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    details = details[details["数量"] > 0]
    return details.reset_index(drop=True)


def add_optional_columns(df):
    defaults = {
        "货柜号": "", "品类": "", "品牌": "", "成本": 0,
        "状态": "未到货", "备注": "",
    }
    for column, default in defaults.items():
        if column not in df.columns:
            df[column] = default
    return df


def build_container_schedule_preview(df):
    if df.empty or "发货日期" not in df.columns:
        return pd.DataFrame()
    preview = df[[
        column for column in ["发货日期", "预计运输天数", "货柜号"]
        if column in df.columns
    ]].copy()
    preview["发货日期"] = pd.to_datetime(preview["发货日期"], errors="coerce").dt.date
    if "预计运输天数" not in preview.columns:
        preview["预计运输天数"] = DEFAULT_TRANSIT_DAYS
    preview["预计运输天数"] = pd.to_numeric(
        preview["预计运输天数"], errors="coerce"
    ).fillna(DEFAULT_TRANSIT_DAYS).clip(lower=1).astype(int)
    preview["预计到货日期"] = preview.apply(
        lambda row: row["发货日期"] + timedelta(days=row["预计运输天数"])
        if pd.notna(row["发货日期"]) else None,
        axis=1,
    )
    return preview.dropna(subset=["发货日期"])


def build_container_display(df, include_cost=False):
    columns = container_display_columns(include_cost)
    if df.empty:
        return pd.DataFrame(columns=columns)

    display = df.copy()
    for column in ["shipped_date", "expected_arrival_date", "actual_arrival_date"]:
        display[column] = pd.to_datetime(display[column], errors="coerce").dt.date
    missing_arrival = date(1900, 1, 1)
    display["actual_arrival_date"] = display["actual_arrival_date"].fillna(
        missing_arrival
    )
    for column in ["container_no", "category", "brand", "material", "note"]:
        display[column] = display[column].fillna("")
    display["department"] = display["department"].fillna(DEFAULT_DEPARTMENT)
    index = [
        "container_key", "shipped_date", "expected_arrival_date", "actual_arrival_date",
        "container_no", "department",
        "category", "brand", "material", "color",
        *(["unit_cost"] if include_cost else []), "status", "note",
    ]
    pivot = display.pivot_table(
        index=index, columns="size", values="quantity", aggfunc="sum", fill_value=0
    ).reset_index()
    for size in SIZE_COLUMNS:
        if size not in pivot.columns:
            pivot[size] = 0
        pivot[size] = pd.to_numeric(pivot[size], errors="coerce").fillna(0).astype(int)
    pivot["总件数"] = pivot[SIZE_COLUMNS].sum(axis=1)
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
        "container_no": "货柜号", "department": "部门", "category": "品类",
        "brand": "品牌", "material": "材质", "color": "颜色",
        "unit_cost": "成本", "status": "状态", "note": "备注",
    })
    pivot["批次标识"] = pivot.apply(
        lambda row: row["货柜号"] or f"{row['发货日期']}-{row['总件数']}", axis=1
    )
    return pivot[columns]


def container_display_columns(include_cost):
    cost = ["成本"] if include_cost else []
    return [
        "货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期",
        "实际到货日期", "货柜号",
        "部门", "品类", "品牌", "材质", "颜色", *cost,
        *SIZE_COLUMNS, "总件数", "状态", "备注",
    ]
