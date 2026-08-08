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


def allocate_brand_merged_sales(lines, inventory_df, invoice_date, invoice_number):
    """Allocate brandless sale demand to real brand SKUs without losing audit data."""
    normalized = normalize_sales_lines(lines)
    inventory = pd.DataFrame(inventory_df).copy()
    for column in ["brand", "material", "color", "size"]:
        if column not in inventory:
            inventory[column] = ""
        inventory[column] = inventory[column].fillna("").astype(str).str.strip()
    inventory["size"] = inventory["size"].str.upper()
    quantity = (
        inventory["quantity"]
        if "quantity" in inventory
        else pd.Series(0, index=inventory.index)
    )
    inventory["quantity"] = pd.to_numeric(
        quantity, errors="coerce"
    ).fillna(0).astype(int)
    inventory["_priority"] = inventory["brand"].ne("临时进货").astype(int)
    inventory = inventory.sort_values(
        ["material", "color", "size", "_priority", "brand"], kind="stable"
    ).reset_index(drop=True)

    demand = normalized.groupby(
        ["材质", "颜色", "尺码"], as_index=False
    )["数量"].sum()
    adjustments = []
    issues = []
    for row in demand.to_dict("records"):
        matches = (
            (inventory["material"] == row["材质"])
            & (inventory["color"] == row["颜色"])
            & (inventory["size"] == row["尺码"])
        )
        candidates = inventory[matches & inventory["quantity"].gt(0)]
        available = int(candidates["quantity"].sum())
        requested = int(row["数量"])
        if available < requested:
            issues.append({
                "品牌": "全部品牌", "材质": row["材质"],
                "颜色": row["颜色"], "尺码": row["尺码"],
                "数量": requested, "当前库存": available,
                "缺口": requested - available, "问题": "库存不足",
            })
            continue
        remaining = requested
        for index, item in candidates.iterrows():
            if remaining <= 0:
                break
            quantity = min(remaining, int(item["quantity"]))
            adjustments.append({
                "日期": invoice_date, "操作": "扣减",
                "品牌": item["brand"], "材质": item["material"],
                "颜色": item["color"], "尺码": item["size"],
                "数量": quantity, "成本": pd.NA,
                "备注": f"客户销售出库｜{invoice_number}",
            })
            inventory.at[index, "quantity"] -= quantity
            remaining -= quantity
    adjustment_columns = [
        "日期", "操作", "品牌", "材质", "颜色", "尺码",
        "数量", "成本", "备注",
    ]
    issue_columns = [
        "品牌", "材质", "颜色", "尺码", "数量", "当前库存", "缺口", "问题",
    ]
    return (
        pd.DataFrame(adjustments, columns=adjustment_columns),
        pd.DataFrame(issues, columns=issue_columns),
    )


def save_sales_invoice(
    supabase, company, customer, invoice, lines, created_by,
    inventory_adjustments=None,
):
    normalized = normalize_sales_lines(lines)
    if normalized.empty:
        raise ValueError("销售出库明细不能为空")
    if not str(company.get("company_name") or "").strip():
        raise ValueError("我方公司名称不能为空")
    if not str(customer.get("display_name") or "").strip():
        raise ValueError("客户名称不能为空")
    adjustments = (
        build_sales_adjustments(
            normalized, invoice["invoice_date"], invoice["invoice_number"]
        )
        if inventory_adjustments is None
        else pd.DataFrame(inventory_adjustments).copy()
    )
    if int(adjustments["数量"].sum()) != int(normalized["数量"].sum()):
        raise ValueError("销售数量与实际库存扣减数量不一致")
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
