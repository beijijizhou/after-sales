from io import BytesIO, StringIO

import pandas as pd


COLUMN_ALIASES = {
    "external_order_id": ("订单号", "订单编码", "订单ID", "Order ID", "order_id"),
    "tracking_number": (
        "物流单号", "运单号", "Tracking Number", "tracking_number",
        "Tracking No",
    ),
    "merchant_order_id": ("客户订单号", "商户订单号", "销售订单号"),
    "carrier": ("物流方式", "物流商", "承运商", "Carrier"),
    "erp_platform": ("平台", "ERP", "ERP平台"),
    "erp_account": ("账号", "ERP账号"),
    "department": ("部门",),
    "label_url": ("面单链接", "面单PDF", "Label URL"),
    "backup_label_url": ("备用面单链接", "备用面单PDF"),
}


def parse_logistics_upload(file_bytes, filename, defaults=None):
    frame = _read_upload(file_bytes, filename)
    frame.columns = [str(column).strip() for column in frame.columns]
    columns = {
        target: next((name for name in aliases if name in frame.columns), None)
        for target, aliases in COLUMN_ALIASES.items()
    }
    missing = [
        label for target, label in (
            ("external_order_id", "订单号"),
            ("tracking_number", "物流单号"),
        ) if not columns[target]
    ]
    if missing:
        raise ValueError("导入文件缺少必填列：" + "、".join(missing))

    defaults = defaults or {}
    rows, issues = [], []
    for index, source in frame.iterrows():
        order_id = _text(source.get(columns["external_order_id"]))
        tracking = _text(source.get(columns["tracking_number"]))
        if not order_id and not tracking:
            continue
        if not order_id or not tracking:
            issues.append(
                f"第 {index + 2} 行缺少"
                + ("订单号" if not order_id else "物流单号")
            )
            continue
        rows.append({
            "tenant_code": defaults.get("tenant_code", "default"),
            "erp_platform": _field(source, columns, "erp_platform")
            or defaults.get("erp_platform", "客户导入"),
            "erp_account": _field(source, columns, "erp_account")
            or defaults.get("erp_account", "默认账号"),
            "department": _field(source, columns, "department")
            or defaults.get("department", ""),
            "external_order_id": order_id,
            "merchant_order_id": _field(source, columns, "merchant_order_id"),
            "tracking_number": tracking,
            "carrier": _field(source, columns, "carrier"),
            "erp_status": defaults.get("erp_status", "客户导入"),
            "label_url": _field(source, columns, "label_url") or None,
            "backup_label_url": _field(
                source, columns, "backup_label_url"
            ) or None,
            "local_acceptance_status": defaults.get(
                "local_acceptance_status", "待核对"
            ),
            "source_payload": {
                str(key): _text(value) for key, value in source.items()
            },
        })
    return rows, issues


def parse_logistics_paste(raw_text, has_header=True, defaults=None):
    lines = [line for line in str(raw_text or "").splitlines() if line.strip()]
    if has_header and lines:
        lines = lines[1:]
    defaults = defaults or {}
    rows, issues = [], []
    for index, line in enumerate(lines, start=2 if has_header else 1):
        values = _split_pasted_line(line)
        if len(values) < 2:
            issues.append(f"第 {index} 行不是两列，请检查订单号和物流单号")
            continue
        order_id, tracking = (_text(values[0]), _text(values[1]))
        if not order_id or not tracking:
            issues.append(
                f"第 {index} 行缺少"
                + ("订单号" if not order_id else "物流单号")
            )
            continue
        rows.append({
            "tenant_code": defaults.get("tenant_code", "default"),
            "erp_platform": defaults.get("erp_platform", "客户粘贴"),
            "erp_account": defaults.get("erp_account", "默认账号"),
            "department": defaults.get("department", ""),
            "external_order_id": order_id,
            "merchant_order_id": "",
            "tracking_number": tracking,
            "carrier": "",
            "erp_status": "客户粘贴",
            "label_url": None,
            "backup_label_url": None,
            "local_acceptance_status": "待核对",
            "source_payload": {
                "订单号": order_id, "物流单号": tracking,
            },
        })
    return rows, issues


def parse_logistics_frame(frame, defaults=None):
    defaults = defaults or {}
    rows, issues = [], []
    for index, source in pd.DataFrame(frame).iterrows():
        order_id = _text(source.get("订单号"))
        tracking = _text(source.get("物流单号"))
        if not order_id and not tracking:
            continue
        if not order_id or not tracking:
            issues.append(
                f"第 {index + 1} 行缺少"
                + ("订单号" if not order_id else "物流单号")
            )
            continue
        rows.append({
            "tenant_code": defaults.get("tenant_code", "default"),
            "erp_platform": defaults.get("erp_platform", "客户粘贴"),
            "erp_account": defaults.get("erp_account", "默认账号"),
            "department": defaults.get("department", ""),
            "external_order_id": order_id,
            "merchant_order_id": "",
            "tracking_number": tracking,
            "carrier": "",
            "erp_status": "客户粘贴",
            "label_url": None,
            "backup_label_url": None,
            "local_acceptance_status": "待核对",
            "source_payload": {
                "订单号": order_id, "物流单号": tracking,
            },
        })
    return rows, issues


def _split_pasted_line(line):
    if "\t" in line:
        return line.split("\t")
    if "," in line:
        return line.split(",")
    return line.split()


def _read_upload(file_bytes, filename):
    suffix = str(filename or "").casefold()
    if suffix.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(file_bytes))
    return pd.read_csv(StringIO(file_bytes.decode("utf-8-sig")))


def _field(source, columns, target):
    column = columns.get(target)
    return _text(source.get(column)) if column else ""


def _text(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
