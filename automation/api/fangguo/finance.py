from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import pandas as pd

from automation.api.fangguo.client import _authenticated_client, _build_headers


API_URL = (
    "https://fangguo.com/fgapp/statistics/basic/factory/"
    "transaction-merge-line/v2/page"
)
NEW_YORK = ZoneInfo("America/New_York")
PAGE_SIZE = 2_000
MAX_PAGES = 500
FEE_TYPES = [
    "ACTUAL_DEDUCTION", "REFUND", "RECHARGE", "PRE_TO_ACTUAL",
    "RETURN_TO_PRE",
]
LINE_IDENTITY_FIELDS = [
    "materialCode", "colorCode", "modelCode", "skuPropertiesName",
]
PRICE_RULE_FIELDS = ["materialCode"]


def fetch_fangguo_finance_lines(
    start_date, end_date, credentials, group_ids,
    report_progress=None, page_size=PAGE_SIZE,
):
    if start_date > end_date:
        raise ValueError("方果财务查询结束日期不能早于开始日期")
    normalized_groups = [int(value) for value in group_ids if str(value).strip()]

    report = report_progress or (lambda _message: None)
    client, token = _authenticated_client(credentials)
    headers = _build_headers(credentials, token)
    start_ms = _milliseconds(datetime.combine(start_date, time.min, NEW_YORK))
    end_ms = _milliseconds(datetime.combine(end_date, time.max, NEW_YORK))
    rows = []
    for page_no in range(1, MAX_PAGES + 1):
        report(f"正在读取方果平台财务第 {page_no} 页")
        response = client.post(
            API_URL,
            headers={
                **headers,
                "Referer": "https://fangguo.com/factory/data/fundDetail",
            },
            json=_finance_payload(
                page_no, page_size, start_ms, end_ms, normalized_groups
            ),
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError(payload.get("msg") or "方果财务接口返回未知错误")
        page_rows = (payload.get("data") or {}).get("list") or []
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
    else:
        raise ValueError("方果财务数据超过安全分页上限，请缩短查询日期")

    normalized = normalize_fangguo_finance_lines(rows)
    report(f"方果平台财务读取完成：{len(normalized):,} 行")
    return normalized


def normalize_fangguo_finance_lines(rows):
    records = []
    for row in rows:
        if not isinstance(row, list):
            continue
        record = {
            str(cell.get("prop")): cell.get("value")
            for cell in row
            if isinstance(cell, dict) and cell.get("prop")
        }
        if record:
            records.append(record)
    if not records:
        return pd.DataFrame()
    result = pd.DataFrame(records)
    dedupe = [name for name in ("tid", *LINE_IDENTITY_FIELDS) if name in result]
    if dedupe:
        result = result.drop_duplicates(subset=dedupe, keep="last")
    return result.reset_index(drop=True)


def build_price_rule_table(lines, price_rule_fields=None):
    rule_fields = list(price_rule_fields or PRICE_RULE_FIELDS)
    columns = [*rule_fields, "currentUnitPrice", "newUnitPrice"]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    source = lines.copy()
    for field in rule_fields:
        if field not in source:
            source[field] = ""
        source[field] = source[field].fillna("").astype(str)
    quantity = pd.to_numeric(source.get("quantity"), errors="coerce").fillna(0)
    amount = pd.to_numeric(source.get("caseAmount"), errors="coerce").fillna(0)
    source["currentUnitPrice"] = (amount / quantity.where(quantity.ne(0))).round(4)
    rules = (
        source.groupby(rule_fields, dropna=False)["currentUnitPrice"]
        .agg(_price_list)
        .reset_index()
    )
    rules["newUnitPrice"] = pd.NA
    return rules[columns]


def recalculate_fangguo_finance(lines, price_rules, price_rule_fields=None):
    if lines.empty:
        return lines.copy()
    rule_fields = list(price_rule_fields or PRICE_RULE_FIELDS)
    rules = price_rules.copy()
    for field in rule_fields:
        rules[field] = rules[field].fillna("").astype(str)
    rules["newUnitPrice"] = pd.to_numeric(
        rules["newUnitPrice"], errors="coerce"
    )
    if rules.duplicated(rule_fields, keep=False).any():
        raise ValueError("新价格表包含重复的定价组合")

    result = lines.copy()
    for field in rule_fields:
        if field not in result:
            result[field] = ""
        result[field] = result[field].fillna("").astype(str)
    result = result.merge(
        rules[[*rule_fields, "newUnitPrice"]],
        on=rule_fields, how="left", validate="many_to_one",
    )
    result["quantity"] = pd.to_numeric(
        result.get("quantity"), errors="coerce"
    ).fillna(0)
    result["caseAmount"] = pd.to_numeric(
        result.get("caseAmount"), errors="coerce"
    ).fillna(0)
    result["totalAmount"] = pd.to_numeric(
        result.get("totalAmount"), errors="coerce"
    ).fillna(0)
    result["recalculatedCaseAmount"] = [
        _money(quantity * price) if pd.notna(price) else old
        for quantity, price, old in zip(
            result["quantity"], result["newUnitPrice"], result["caseAmount"]
        )
    ]
    result["difference"] = (
        result["recalculatedCaseAmount"] - result["caseAmount"]
    ).round(4)
    result["recalculatedTotalAmount"] = (
        result["totalAmount"] + result["difference"]
    ).round(4)
    result["priceRuleApplied"] = result["newUnitPrice"].notna()
    return result


def build_customer_bill_summary(lines):
    columns = [
        "customerAccount", "orderCount", "quantity", "originalAmount",
        "recalculatedAmount", "amountDue",
    ]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    source = lines.copy()
    source["customerAccount"] = source.apply(_customer_account, axis=1)
    source = source[source["customerAccount"].notna()]
    if source.empty:
        return pd.DataFrame(columns=columns)
    result = source.groupby("customerAccount", sort=False).agg(
        orderCount=("tid", "nunique"),
        quantity=("quantity", "sum"),
        originalAmount=("totalAmount", "sum"),
        recalculatedAmount=("recalculatedTotalAmount", "sum"),
        amountDue=("difference", "sum"),
    ).reset_index()
    for column in ("originalAmount", "recalculatedAmount", "amountDue"):
        result[column] = result[column].round(4)
    return result[columns]


def build_customer_bill_table(lines, account, include_model=True):
    columns = [
        "materialCode", "modelCode", "orderCount", "quantity",
        "newUnitPrice", "originalMaterialAmount", "originalAmount",
        "recalculatedAmount", "amountDue",
    ]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    source = lines.copy()
    source["customerAccount"] = source.apply(_customer_account, axis=1)
    source = source[source["customerAccount"] == account].copy()
    if source.empty:
        return pd.DataFrame(columns=columns)
    for field in ("materialCode", "modelCode"):
        if field not in source:
            source[field] = ""
        source[field] = source[field].fillna("").astype(str)
    group_fields = ["materialCode", "modelCode"] if include_model else ["materialCode"]
    grouped = source.groupby(group_fields, dropna=False, sort=False).agg(
        orderCount=("tid", "nunique"),
        quantity=("quantity", "sum"),
        newUnitPrice=("newUnitPrice", _single_price),
        originalMaterialAmount=("caseAmount", "sum"),
        originalAmount=("totalAmount", "sum"),
        recalculatedAmount=("recalculatedTotalAmount", "sum"),
        amountDue=("difference", "sum"),
    ).reset_index()
    if not include_model:
        grouped["modelCode"] = ""
    for column in (
        "originalMaterialAmount", "originalAmount",
        "recalculatedAmount", "amountDue",
    ):
        grouped[column] = grouped[column].round(4)
    total = {
        "materialCode": "合计", "modelCode": "",
        "orderCount": source["tid"].nunique(),
        "quantity": source["quantity"].sum(), "newUnitPrice": "",
        "originalMaterialAmount": round(source["caseAmount"].sum(), 4),
        "originalAmount": round(source["totalAmount"].sum(), 4),
        "recalculatedAmount": round(source["recalculatedTotalAmount"].sum(), 4),
        "amountDue": round(source["difference"].sum(), 4),
    }
    return pd.concat(
        [grouped[columns], pd.DataFrame([total], columns=columns)],
        ignore_index=True,
    )


def _finance_payload(page_no, page_size, start_ms, end_ms, group_ids):
    return {
        "pageNo": page_no, "pageSize": page_size, "total": 0,
        "transactionStartTime": start_ms, "transactionEndTime": end_ms,
        "pushStartTime": None, "pushEndTime": None,
        "payStartTime": None, "payEndTime": None,
        "auditStartTime": None, "auditEndTime": None,
        "platformTradeTypeList": [], "deptIdList": [],
        "tenantIdList": [], "tidList": [], "cpNumList": [],
        "storeIdList": [], "cpCodeList": [], "itemCode": "",
        "combinationDecode": None, "combinedFlag": None,
        "materialCode": "", "colorCode": "", "modelCode": "",
        "businessNodeList": [], "feeTypeList": FEE_TYPES,
        "feeNameTypeList": [], "jitFlag": None,
        "groupIdList": group_ids, "deliveryWarehouse": None,
        "dfStatus": None,
    }


def _price_list(values):
    prices = sorted({float(value) for value in values.dropna()})
    return " / ".join(f"{value:.4f}" for value in prices)


def _single_price(values):
    prices = sorted({float(value) for value in values.dropna()})
    if not prices:
        return None
    if len(prices) == 1:
        return prices[0]
    return " / ".join(f"{value:.4f}" for value in prices)


def _money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def _milliseconds(value):
    return int(value.timestamp() * 1_000)


def _customer_account(row):
    name = str(row.get("shopName") or "").strip()
    code = str(row.get("shopCode") or "").strip().casefold()
    if code == "haloo" or name == "海捞":
        return "Haloo"
    if name.startswith("隆丰"):
        return "隆丰"
    return None
