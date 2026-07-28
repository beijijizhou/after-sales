import pandas as pd

from db.inventory.core.constants import UV_MODEL_ORDER


def uses_model_rows(df):
    if df.empty or "department" not in df:
        return False
    departments = {
        str(value).strip().upper()
        for value in df["department"].dropna()
        if str(value).strip()
    }
    return bool(departments) and "DTF" not in departments


def build_model_container_display(df, include_cost=False):
    display = df.copy()
    for column in [
        "shipped_date", "expected_arrival_date", "actual_arrival_date",
    ]:
        display[column] = pd.to_datetime(
            display[column], errors="coerce"
        ).dt.date
    if "actual_arrival_at" in display.columns:
        arrival_at = pd.to_datetime(
            display["actual_arrival_at"], errors="coerce", utc=True
        )
        display["actual_arrival_at"] = arrival_at.dt.tz_convert(
            "America/New_York"
        ).dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
    else:
        display["actual_arrival_at"] = ""
    for column in [
        "container_no", "category", "brand", "material", "color",
        "size", "note",
    ]:
        display[column] = display[column].fillna("").astype(str).str.strip()
    display["department"] = display["department"].fillna("")
    display["quantity"] = pd.to_numeric(
        display["quantity"], errors="coerce"
    ).fillna(0).astype(int)
    cost_column = ["unit_cost"] if include_cost else []
    index = [
        "container_key", "shipped_date", "expected_arrival_date",
        "actual_arrival_date", "actual_arrival_at", "container_no",
        "department", "category",
        "brand", "material", "color", "size", *cost_column,
        "status", "note",
    ]
    result = (
        display.groupby(index, dropna=False, as_index=False)["quantity"]
        .sum()
        .rename(columns={
            "container_key": "货柜记录ID",
            "shipped_date": "发货日期",
            "expected_arrival_date": "预计到货日期",
            "actual_arrival_date": "实际到货日期",
            "actual_arrival_at": "实际到货时间（纽约）",
            "container_no": "货柜号",
            "department": "部门",
            "category": "品类",
            "brand": "品牌",
            "material": "材质",
            "color": "颜色",
            "size": "型号",
            "unit_cost": "成本",
            "quantity": "数量",
            "status": "状态",
            "note": "备注",
        })
    )
    result["运输天数"] = (
        result["预计到货日期"] - result["发货日期"]
    ).apply(lambda duration: duration.days)
    result["总件数"] = result["数量"]
    result["批次标识"] = result.apply(
        lambda row: row["货柜号"] or (
            f"{row['发货日期']}-{row['货柜记录ID']}"
        ),
        axis=1,
    )
    model_order = {
        value.upper(): index for index, value in enumerate(UV_MODEL_ORDER)
    }
    result["_model_order"] = (
        result["型号"].str.upper().map(model_order).fillna(99)
    )
    result = result.sort_values(
        ["货柜记录ID", "材质", "_model_order", "型号"],
        kind="stable",
    ).drop(columns="_model_order")
    cost = ["成本"] if include_cost else []
    columns = [
        "货柜记录ID", "批次标识", "发货日期", "运输天数",
        "预计到货日期", "实际到货日期", "实际到货时间（纽约）",
        "货柜号", "部门", "品类",
        "品牌", "材质", "颜色", *cost, "型号", "数量",
        "总件数", "状态", "备注",
    ]
    return result[columns].reset_index(drop=True)
