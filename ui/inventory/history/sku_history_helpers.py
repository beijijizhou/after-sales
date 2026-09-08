"""Formatting and matching helpers for SKU operation history."""

from zoneinfo import ZoneInfo

import pandas as pd

from utils.daily_consumption import daily_consumption_business_type
from utils.inventory_movements import is_stocktake_reason, movement_business_type


def movement_operation(change, reason):
    if is_stocktake_reason(reason):
        return "库存设置"
    if change > 0:
        return "入库"
    if change < 0:
        return "出库"
    return "库存记录"


def movement_source(record, reason):
    business_type = movement_business_type(reason)
    consumption_type = daily_consumption_business_type(reason)
    source = business_type or consumption_type or record.get("source_type")
    parts = [
        str(value).strip() for value in [source, reason]
        if str(value or "").strip()
    ]
    return "｜".join(dict.fromkeys(parts)) or "—"


def optional_int(value):
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed)


def display_number(value):
    return "—" if value is None else f"{int(value):,}"


def signed(value):
    number = int(value or 0)
    return f"+{number:,}" if number > 0 else f"{number:,}"


def date_text(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return "—" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def snapshot_matches(snapshot, selected):
    if not isinstance(snapshot, dict):
        return False
    fields = ["category", "brand", "material", "color"]
    if snapshot.get("size") not in (None, ""):
        fields.append("size")
    return all(
        str(snapshot.get(field) or "").strip()
        == str(selected.get(field) or "").strip()
        for field in fields
    )


def changed_fields(old, new):
    labels = {
        "category": "品类", "brand": "品牌", "material": "材质",
        "color": "颜色", "size": "尺码/型号", "unit": "单位",
        "sku_name": "SKU 名称", "is_active": "状态",
    }
    changes = []
    for field, label in labels.items():
        before = old.get(field) if isinstance(old, dict) else None
        after = new.get(field) if isinstance(new, dict) else None
        if before == after:
            continue
        if field == "is_active":
            before = "启用" if before else "停用"
            after = "启用" if after else "停用"
        changes.append(f"{label}：{before or '未填写'} → {after or '未填写'}")
    return changes


def change_operation(old, new, changed):
    before = old.get("is_active") if isinstance(old, dict) else None
    after = new.get("is_active") if isinstance(new, dict) else None
    if before is True and after is False:
        return "停用 SKU"
    if before is False and after is True:
        return "启用 SKU"
    return "修改 SKU 资料" if changed else "SKU 更新"


def new_york_time(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "—"
    return parsed.tz_convert(ZoneInfo("America/New_York")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def filter_exact_sku(frame, selected):
    if frame.empty:
        return frame
    result = frame
    for column, value in selected.items():
        if column not in result:
            return result.iloc[0:0]
        result = result[result[column].fillna("").astype(str) == value]
    return result.reset_index(drop=True)
