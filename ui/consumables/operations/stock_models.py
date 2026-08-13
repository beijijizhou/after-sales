"""Pure models shared by consumable stock workflows."""

import pandas as pd

from ui.consumables.units import boxes_to_base, to_boxes


def build_daily_issue_template(label_to_row):
    return pd.DataFrame([{
        "耗材 SKU": label,
        "当前库存（箱）": float(item["current_quantity"]) / float(item["units_per_package"]),
        "每箱数量": float(item["units_per_package"]),
        "今日领用（箱）": 0,
        "备注": "",
    } for label, item in label_to_row.items()])


def normalize_initialization(edited, label_to_row, include_cost):
    rows, preview = [], []
    for row in edited.to_dict("records"):
        label = row["耗材 SKU"]
        item = label_to_row[label]
        current_boxes = to_boxes(item["current_quantity"], item)
        target_boxes = pd.to_numeric(row.get("目标库存（箱）", row.get("目标库存")), errors="coerce")
        if current_boxes is None or pd.isna(target_boxes) or target_boxes < 0:
            continue
        target = boxes_to_base(target_boxes, item)
        difference = float(target) - float(item["current_quantity"])
        if abs(difference) < 0.00005:
            continue
        record = {"item_id": item["id"], "quantity": difference, "note": row.get("备注") or ""}
        cost = pd.to_numeric(row.get("单位成本"), errors="coerce")
        if include_cost and not pd.isna(cost):
            record["unit_cost"] = float(cost)
        rows.append(record)
        preview.append({
            "耗材 SKU": label, "当前库存（箱）": current_boxes,
            "目标库存（箱）": float(target_boxes),
            "库存差额（箱）": float(target_boxes) - current_boxes,
            **({"单位成本": record.get("unit_cost")} if include_cost else {}),
        })
    return rows, pd.DataFrame(preview)


def prepare_preview(preview):
    display = preview.copy()
    if "本次变动（箱）" in display:
        values = pd.to_numeric(display["本次变动（箱）"], errors="coerce").fillna(0)
        operation = "本次出库 (-)" if values.le(0).all() else "本次入库 (+)" if values.ge(0).all() else "本次变动 (+/-)"
        return display.rename(columns={"本次变动（箱）": operation, "操作后库存（箱）": "调整后库存（箱）"})
    if "库存差额（箱）" in display:
        return display.rename(columns={"库存差额（箱）": "本次变动 (+/-)", "目标库存（箱）": "调整后库存（箱）"})
    return display
