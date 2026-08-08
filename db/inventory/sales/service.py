from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd


SALES_LINE_COLUMNS = [
    "品牌", "材质", "颜色", "尺码", "数量", "单价", "金额",
]


def build_invoice_number(now=None):
    current = now or datetime.now(ZoneInfo("America/New_York"))
    return f"INV-{current:%Y%m%d}-{uuid4().hex[:6].upper()}"


def build_sales_draft_signature(company, customer, invoice, lines):
    payload = {
        "company": company,
        "customer": customer,
        "invoice": invoice,
        "lines": normalize_sales_lines(lines).to_dict("records"),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def normalize_sales_lines(source):
    result = pd.DataFrame(source).copy()
    for column in ["品牌", "材质", "颜色", "尺码"]:
        if column not in result:
            result[column] = ""
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["尺码"] = result["尺码"].str.upper()
    for column in ["数量", "单价"]:
        if column not in result:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    result["数量"] = result["数量"].astype(int)
    result = result[
        (result["材质"] != "")
        & (result["颜色"] != "")
        & (result["尺码"] != "")
        & (result["数量"] > 0)
        & (result["单价"] >= 0)
    ].copy()
    result["金额"] = result.apply(
        lambda row: float(
            (Decimal(str(row["数量"])) * Decimal(str(row["单价"])))
            .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ),
        axis=1,
    )
    return result[SALES_LINE_COLUMNS].reset_index(drop=True)


def build_sales_adjustments(lines, invoice_date, invoice_number):
    normalized = normalize_sales_lines(lines)
    if normalized.empty:
        return pd.DataFrame(columns=[
            "日期", "操作", "品牌", "材质", "颜色", "尺码",
            "数量", "成本", "备注",
        ])
    return pd.DataFrame({
        "日期": [invoice_date] * len(normalized),
        "操作": ["扣减"] * len(normalized),
        "品牌": normalized["品牌"],
        "材质": normalized["材质"],
        "颜色": normalized["颜色"],
        "尺码": normalized["尺码"],
        "数量": normalized["数量"],
        "成本": [pd.NA] * len(normalized),
        "备注": [f"客户销售出库｜{invoice_number}"] * len(normalized),
    })


def save_sales_invoice(
    supabase, company, customer, invoice, lines, created_by,
):
    normalized = normalize_sales_lines(lines)
    if normalized.empty:
        raise ValueError("销售出库明细不能为空")
    if not str(company.get("company_name") or "").strip():
        raise ValueError("我方公司名称不能为空")
    if not str(customer.get("display_name") or "").strip():
        raise ValueError("客户名称不能为空")
    adjustments = build_sales_adjustments(
        normalized, invoice["invoice_date"], invoice["invoice_number"]
    )
    inventory_rows = [{
        "brand": row["品牌"],
        "material": row["材质"],
        "color": row["颜色"],
        "size": row["尺码"],
        "quantity_change": -int(row["数量"]),
        "movement_date": row["日期"].isoformat(),
        "reason": row["备注"],
    } for row in adjustments.to_dict("records")]
    line_rows = [{
        "brand": row["品牌"], "material": row["材质"],
        "color": row["颜色"], "size": row["尺码"],
        "quantity": int(row["数量"]), "unit_price": float(row["单价"]),
    } for row in normalized.to_dict("records")]
    response = supabase.rpc("create_inventory_sales_invoice", {
        "p_company": company,
        "p_customer": customer,
        "p_invoice": {
            **invoice,
            "invoice_date": invoice["invoice_date"].isoformat(),
        },
        "p_lines": line_rows,
        "p_inventory_rows": inventory_rows,
        "p_created_by": created_by,
    }).execute()
    return response.data, normalized
