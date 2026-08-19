"""Pure models shared by consumable stock workflows."""

import pandas as pd

from ui.consumables.units import boxes_to_base, to_boxes
from ui.operations import prepare_stock_change_display


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


def build_stock_review_comparison(preview):
    """Adapt legacy consumable previews to the cross-ledger stock contract."""
    comparison = pd.DataFrame(preview).copy()
    if comparison.empty:
        return comparison
    if {
        "当前库存", "本次变动", "调整后库存",
    }.issubset(comparison.columns):
        return comparison
    if {
        "当前库存", "本次变动", "操作后库存",
    }.issubset(comparison.columns):
        # Package-based entry previews already expose the three business
        # quantities in their selected entry unit.  They may additionally
        # carry explicit box columns for audit detail.  Renaming those box
        # columns here would create duplicate ``当前库存``/``本次变动`` labels,
        # which pandas cannot normalize as a one-dimensional Series.
        return comparison.rename(columns={"操作后库存": "调整后库存"})
    if "本次变动（箱）" in comparison:
        return comparison.rename(columns={
            "当前库存（箱）": "当前库存",
            "本次变动（箱）": "本次变动",
            "操作后库存（箱）": "调整后库存",
        })
    if "库存差额（箱）" in comparison:
        return comparison.rename(columns={
            "当前库存（箱）": "当前库存",
            "库存差额（箱）": "本次变动",
            "目标库存（箱）": "调整后库存",
        })
    return comparison


def prepare_preview(preview, action=None):
    """Compatibility adapter for callers that need the display DataFrame."""
    comparison = build_stock_review_comparison(preview)
    if comparison.empty or not {
        "当前库存", "本次变动", "调整后库存",
    }.issubset(comparison.columns):
        return comparison
    return prepare_stock_change_display(comparison, action=action)[0]
