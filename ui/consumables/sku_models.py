"""Pure table transformations for consumable SKU administration."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from ui.consumables.units import boxes_to_base, to_boxes

EDIT_COLUMNS = ["分类", "耗材名称", "规格/型号", "品牌", "基础单位", "包装单位", "每箱数量", "最低库存（箱）", "当前库存（箱）", "启用"]


def copy_options(items):
    if items is None or items.empty:
        return [""], {"": "不复制，从空白新增"}
    labels = {"": "不复制，从空白新增"}
    for row in items.to_dict("records"):
        labels[str(row["id"])] = "｜".join(
            str(value).strip() for value in (
                row.get("category"), row.get("name"), row.get("specification"), row.get("brand")
            ) if pd.notna(value) and str(value).strip()
        )
    return list(labels), labels


def copy_defaults(items, source_id):
    defaults = {"category": "", "name": "", "specification": "", "brand": "", "base_unit": "", "units_per_package": 1.0, "minimum_boxes": None}
    if not source_id or items is None or items.empty:
        return defaults
    matches = items[items["id"].astype(str) == str(source_id)]
    if matches.empty:
        return defaults
    row = matches.iloc[0]
    defaults.update({
        "category": text(row.get("category")), "name": text(row.get("name")),
        "specification": text(row.get("specification")), "brand": text(row.get("brand")),
        "base_unit": text(row.get("base_unit")),
        "units_per_package": float(row.get("units_per_package") or 1),
        "minimum_boxes": to_boxes(row.get("minimum_quantity"), row),
    })
    return defaults


def build_editor(items):
    return pd.DataFrame({
        "_id": items["id"], "分类": items["category"], "耗材名称": items["name"],
        "规格/型号": items["specification"], "品牌": items["brand"], "基础单位": items["base_unit"],
        "包装单位": "箱", "每箱数量": items["units_per_package"],
        "最低库存（箱）": items.apply(lambda row: to_boxes(row["minimum_quantity"], row), axis=1),
        "当前库存（箱）": items.apply(lambda row: to_boxes(row["current_quantity"], row), axis=1),
        "启用": items["is_active"],
    })


def build_updates(original, edited):
    original_by_id = original.set_index("id").to_dict("index")
    updates = []
    for row in edited.to_dict("records"):
        item_id = row["_id"]
        values = {
            "category": required(row["分类"], "分类"), "name": required(row["耗材名称"], "耗材名称"),
            "specification": text(row["规格/型号"]), "brand": text(row["品牌"]),
            "base_unit": required(row["基础单位"], "基础单位"), "package_unit": "箱",
            "units_per_package": number(row["每箱数量"]),
            "minimum_quantity": boxes_to_base(row["最低库存（箱）"], {"package_unit": "箱", "units_per_package": row["每箱数量"]}),
            "is_active": bool(row["启用"]),
        }
        if values["units_per_package"] is None or values["units_per_package"] <= 0:
            raise ValueError(f"{values['name']} 的每箱数量必须大于 0。")
        if any(not same(original_by_id[item_id].get(key), value) for key, value in values.items()):
            values["updated_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
            updates.append((item_id, values))
    return updates


def required(value, label):
    result = text(value)
    if not result:
        raise ValueError(f"{label}不能为空。")
    return result


def text(value):
    return "" if pd.isna(value) else str(value).strip()


def number(value):
    result = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(result) else float(result)


def same(left, right):
    return (pd.isna(left) and right is None) or left == right
