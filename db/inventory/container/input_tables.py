"""Normalize editable container schedules into SKU-level records."""

from datetime import date, timedelta
from uuid import uuid4

import pandas as pd

from db.inventory import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT, SIZE_COLUMNS


CONTAINER_STATUSES = ["在途", "取消"]
DEFAULT_TRANSIT_DAYS = 55
COLOR_REQUIRED_CATEGORIES = {"黑白短袖", "彩色短袖"}


def build_container_template(today=None):
    shipped_date = today or date.today()
    return pd.DataFrame([{
        "发货日期": shipped_date, "预计运输天数": DEFAULT_TRANSIT_DAYS,
        "货柜号": "", "部门": DEFAULT_DEPARTMENT,
        "品类": DEFAULT_CATEGORY, "品牌": "", "材质": "180g",
        "颜色": "", "成本": 0, **{size: 0 for size in SIZE_COLUMNS},
        "状态": "在途", "备注": "",
    }])


def normalize_container_rows(df):
    model_input = {"型号", "数量"}.issubset(df.columns)
    item_columns = {"型号", "数量"} if model_input else set(SIZE_COLUMNS)
    required = {
        "发货日期", "预计运输天数", "部门", "材质", "颜色", *item_columns,
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"缺少列：{', '.join(sorted(missing))}")

    result = add_optional_columns(df.copy())
    result["发货日期"] = pd.to_datetime(
        result["发货日期"], errors="coerce"
    ).dt.date
    result["预计运输天数"] = pd.to_numeric(
        result["预计运输天数"], errors="coerce"
    ).fillna(DEFAULT_TRANSIT_DAYS).clip(lower=1).astype(int)
    result["预计到货日期"] = result.apply(
        lambda row: row["发货日期"] + timedelta(days=int(row["预计运输天数"]))
        if pd.notna(row["发货日期"]) else None, axis=1,
    )
    defaults = [
        ("货柜号", ""), ("部门", DEFAULT_DEPARTMENT), ("品类", ""),
        ("品牌", ""), ("材质", "180g"), ("颜色", ""),
        ("状态", "在途"), ("备注", ""),
    ]
    for column, default in defaults:
        result[column] = result[column].fillna(default).astype(str).str.strip()
    container_keys = {}

    def container_key(row):
        supplied = str(row.get("货柜记录ID") or "").strip()
        if supplied:
            return supplied
        normalized = "".join(row["货柜号"].upper().split())
        return container_keys.setdefault(normalized, normalized) if normalized else str(uuid4())

    result["货柜记录ID"] = result.apply(container_key, axis=1)
    result["成本"] = pd.to_numeric(result["成本"], errors="coerce").fillna(0)
    result.loc[~result["状态"].isin(CONTAINER_STATUSES), "状态"] = "在途"
    result = result.dropna(subset=["发货日期", "预计到货日期"])
    has_required_identity = (result["部门"] != "") & (result["材质"] != "")
    missing_required_color = (
        result["品类"].isin(COLOR_REQUIRED_CATEGORIES)
        & result["颜色"].eq("")
    )
    result = result[has_required_identity & ~missing_required_color]
    identifiers = [
        "货柜记录ID", "发货日期", "预计运输天数", "预计到货日期",
        "货柜号", "部门", "品类", "品牌", "材质", "颜色", "成本",
        "状态", "备注",
    ]
    if model_input:
        result["型号"] = result["型号"].fillna("").astype(str).str.strip()
        result["数量"] = pd.to_numeric(
            result["数量"], errors="coerce"
        ).fillna(0).astype(int)
        details = result.rename(columns={"型号": "尺码"})
        return details[(details["尺码"] != "") & (details["数量"] > 0)][
            [*identifiers, "尺码", "数量"]
        ].reset_index(drop=True)

    for size in SIZE_COLUMNS:
        result[size] = pd.to_numeric(
            result[size], errors="coerce"
        ).fillna(0).astype(int)
    details = result.melt(
        id_vars=identifiers, value_vars=SIZE_COLUMNS,
        var_name="尺码", value_name="数量",
    )
    return details[details["数量"] > 0].reset_index(drop=True)


def add_optional_columns(df):
    defaults = {
        "货柜号": "", "品类": "", "品牌": "", "成本": 0,
        "状态": "在途", "备注": "", "货柜记录ID": "",
    }
    for column, default in defaults.items():
        if column not in df.columns:
            df[column] = default
    return df


def build_container_schedule_preview(df):
    if df.empty or "发货日期" not in df.columns:
        return pd.DataFrame()
    columns = [
        column for column in ["发货日期", "预计运输天数", "货柜号"]
        if column in df.columns
    ]
    preview = df[columns].copy()
    preview["发货日期"] = pd.to_datetime(
        preview["发货日期"], errors="coerce"
    ).dt.date
    if "预计运输天数" not in preview:
        preview["预计运输天数"] = DEFAULT_TRANSIT_DAYS
    preview["预计运输天数"] = pd.to_numeric(
        preview["预计运输天数"], errors="coerce"
    ).fillna(DEFAULT_TRANSIT_DAYS).clip(lower=1).astype(int)
    preview["预计到货日期"] = preview.apply(
        lambda row: row["发货日期"] + timedelta(days=row["预计运输天数"])
        if pd.notna(row["发货日期"]) else None, axis=1,
    )
    return preview.dropna(subset=["发货日期"])
