"""Tracking-number input normalization."""

import re


def parse_tracking_numbers(raw):
    parts = re.split(r"[,，;；\s]+", str(raw or ""))
    return list(dict.fromkeys(part.strip() for part in parts if part.strip()))


def parse_tracking_table(frame):
    if frame is None or frame.empty or "物流单号" not in frame:
        return []
    numbers = []
    for value in frame["物流单号"].fillna("").astype(str):
        numbers.extend(parse_tracking_numbers(value))
    return list(dict.fromkeys(numbers))


def parse_order_tracking_table(frame):
    if frame is None or frame.empty or "物流单号" not in frame:
        return []
    rows = []
    seen = set()
    for item in frame.fillna("").astype(str).to_dict("records"):
        order_number = item.get("订单号", "").strip()
        for tracking_number in parse_tracking_numbers(item.get("物流单号", "")):
            identity = (order_number, tracking_number)
            if identity not in seen:
                rows.append({
                    "订单号": order_number,
                    "物流单号": tracking_number,
                })
                seen.add(identity)
    return rows


def normalize_suggested_rows(values):
    rows = []
    for value in values or []:
        if isinstance(value, dict):
            rows.append({
                "订单号": str(value.get("订单号") or "").strip(),
                "物流单号": str(value.get("物流单号") or "").strip(),
                "面单PDF": value.get("面单PDF"),
                "备用面单PDF": value.get("备用面单PDF"),
                "ERP平台": value.get("ERP平台", ""),
                "ERP账号": value.get("ERP账号", ""),
                "部门": value.get("部门", ""),
                "商户订单号": value.get("商户订单号", ""),
                "物流商": value.get("物流商", ""),
                "面单OCR地址": value.get("面单OCR地址", ""),
                "重量（oz）": value.get("重量（oz）"),
                "重量（lb）": value.get("重量（lb）"),
                "OCR状态": value.get("OCR状态", ""),
            })
        else:
            rows.append({"订单号": "", "物流单号": str(value or "").strip()})
    normalized = []
    seen = set()
    for row in rows:
        for tracking_number in parse_tracking_numbers(row.get("物流单号")):
            identity = (row.get("订单号", ""), tracking_number)
            if identity not in seen:
                normalized.append({**row, "物流单号": tracking_number})
                seen.add(identity)
    return normalized
