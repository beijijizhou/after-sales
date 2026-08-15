import json
import re
from urllib.parse import urljoin

from automation.api.diy19 import DIY19_BASE_URLS, load_diy19_credentials
from automation.api.diy19.auth import USER_AGENT, login_diy19
from automation.integrations.stages import (
    IN_PRODUCTION,
    SHIPPED,
    UNACCEPTED,
    stage_label,
)


ORDER_STATE_BY_STAGE = {
    UNACCEPTED: "0",
    IN_PRODUCTION: "1",
    SHIPPED: "2",
}


def fetch_diy19_shipments(
    platform, credentials, start_date, end_date, stage=1, page_size=1000,
):
    base_url = DIY19_BASE_URLS[platform]
    client = login_diy19(base_url, platform, credentials)
    rows = []
    page_index = 1
    while True:
        response = client.post(
            f"{base_url}/ProduceOrder/List?lang=zh_chs",
            data=_list_form(
                page_index, page_size, start_date, end_date, stage
            ),
            headers=_request_headers(base_url),
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("Code") != 200:
            raise ValueError(
                payload.get("Message") or f"{platform}订单物流读取失败"
            )
        result = json.loads(payload.get("Data") or "{}")
        page_rows = result.get("rows") or []
        rows.extend(
            shipment
            for record in page_rows
            for shipment in _normalize_record(record, platform, base_url)
        )
        page_count = int(result.get("pageCount") or 1)
        if page_index >= page_count or not page_rows:
            break
        page_index += 1
    for row in rows:
        row["local_acceptance_status"] = stage_label(stage)
    return rows


def load_diy19_logistics_credentials(secrets, platform):
    return load_diy19_credentials(secrets, platform)


def _list_form(page_index, page_size, start_date, end_date, stage):
    order_state = ORDER_STATE_BY_STAGE.get(stage)
    if order_state is None:
        raise ValueError(f"19DIY暂不支持订单阶段：{stage}")
    return {
        "PageIndex": str(page_index),
        "PageSize": str(page_size),
        "QueryItems[0][FieldName]": "SYS_DATE_ADD",
        "QueryItems[0][Comparator]": ">=",
        "QueryItems[0][FieldValue]": f"{start_date:%Y/%m/%d} 00:00:00",
        "QueryItems[1][FieldName]": "SYS_DATE_ADD",
        "QueryItems[1][Comparator]": "<=",
        "QueryItems[1][FieldValue]": f"{end_date:%Y/%m/%d} 23:59:59",
        "QueryItems[2][FieldName]": "OrderState",
        "QueryItems[2][Comparator]": "=",
        "QueryItems[2][FieldValue]": order_state,
        "SortItems[0][FieldName]": "SYS_DATE_ADD",
        "SortItems[0][SortSymbol]": "DESC",
    }


def _normalize_record(record, platform, base_url):
    tracking_numbers = _tracking_numbers(
        record.get("LogisticsTrackingNo")
    )
    if not tracking_numbers:
        return []
    label_url = _label_url(record, base_url)
    return [{
        "tenant_code": "default",
        "erp_platform": platform,
        "erp_account": platform,
        "department": "DTF",
        "external_order_id": str(record.get("OrderNo") or "").strip(),
        "merchant_order_id": str(
            record.get("CustomerOrderNo") or ""
        ).strip(),
        "tracking_number": tracking_number,
        "carrier": str(
            record.get("LogisticsMethonAliseName") or ""
        ).strip(),
        "erp_status": str(
            record.get("OrderState_Name") or record.get("OrderState") or ""
        ).strip(),
        "label_url": label_url,
        "backup_label_url": _absolute_url(
            base_url, record.get("LogisticsLabelFileImage")
        ),
        "local_acceptance_status": "未接单",
        "source_payload": record,
    } for tracking_number in tracking_numbers]


def _tracking_numbers(value):
    return [
        item.strip() for item in re.split(r"[,;\r\n]+", str(value or ""))
        if item.strip()
    ]


def _label_url(record, base_url):
    return (
        _absolute_url(base_url, record.get("LogisticsLabelFileOrign"))
        or _absolute_url(base_url, record.get("LogisticsLabelFile"))
    )


def _absolute_url(base_url, value):
    value = str(value or "").strip()
    return urljoin(f"{base_url}/", value) if value else None


def _request_headers(base_url):
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": base_url,
        "Referer": f"{base_url}/ProduceOrder/Index?lang=zh_chs",
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }
