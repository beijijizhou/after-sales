"""Dependency-light client for the official Humbird Open Platform.

Documentation: https://open.hihumbird.com/api/
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
from threading import Lock
from zoneinfo import ZoneInfo

import requests


OPEN_API_URL = "https://open.hihumbird.com/api/router"
PRODUCTION_API_TYPE = "oc.production.item.page"
PRODUCT_API_TYPE = "spu.selection.spu.get"
WAYBILL_API_TYPE = "logistics.waybill.get"
NEW_YORK = ZoneInfo("America/New_York")
PAGE_SIZE = 200
PAGE_WORKERS = 8
STATUS_NAMES = {
    -3: "已取消", -1: "待接单", 1: "已接单", 5: "生产中", 9: "已生产",
}

_PRODUCT_CACHE = {}
_PRODUCT_CACHE_LOCK = Lock()


class HumbirdOpenApiError(RuntimeError):
    pass


def fetch_open_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
    include_product_details=True,
    start_hour=0,
    end_hour=23,
):
    client = HumbirdOpenApiClient(credentials)
    report = report_progress or (lambda _message: None)
    report("1/3 正在通过蜂鸟官方开放 API 读取生产项")
    records = client.production_items(
        start_date, end_date, start_hour=start_hour, end_hour=end_hour
    )
    report(f"2/3 已读取 {len(records):,} 个生产项")
    if include_product_details and records:
        records = _hydrate_product_details(client, records, report)
    report(f"3/3 蜂鸟官方开放 API 读取完成：{len(records):,} 条")
    return records


class HumbirdOpenApiClient:
    def __init__(self, credentials, session=None):
        if isinstance(credentials, str):
            credentials = {"api_key": credentials}
        self.api_key = str((credentials or {}).get("api_key") or "").strip()
        if not self.api_key:
            raise ValueError("蜂鸟开放平台缺少 api_key")
        self.session = session or requests.Session()

    def production_items(
        self, start_date, end_date, statuses=None, start_hour=0, end_hour=23,
    ):
        def fetch_page(page):
            body = {
                "page": page,
                "page_size": PAGE_SIZE,
                "created_range": _date_range(
                    start_date, end_date, start_hour, end_hour
                ),
            }
            if statuses is not None:
                body["status"] = list(statuses)
            return self.post(PRODUCTION_API_TYPE, body)

        first = fetch_page(1)
        rows = list(first.get("list") or [])
        total = int(first.get("total") or 0)
        page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
        if page_count > 1:
            pages = {}
            with ThreadPoolExecutor(
                max_workers=min(PAGE_WORKERS, page_count - 1)
            ) as pool:
                futures = {
                    pool.submit(fetch_page, page): page
                    for page in range(2, page_count + 1)
                }
                for future in as_completed(futures):
                    pages[futures[future]] = list(
                        future.result().get("list") or []
                    )
            for page in sorted(pages):
                rows.extend(pages[page])
        if len(rows) != total:
            raise HumbirdOpenApiError(
                f"{PRODUCTION_API_TYPE} 应返回 {total:,} 条，"
                f"实际收到 {len(rows):,} 条"
            )
        return _deduplicate(rows, "code")

    def product(self, spu_id):
        return self.get(
            PRODUCT_API_TYPE,
            {"id": str(spu_id), "accept_sku_info": "true"},
        )

    def waybill(self, order_no):
        return self.post(WAYBILL_API_TYPE, {"order_no": str(order_no)})

    def post(self, api_type, payload):
        response = self.session.post(
            OPEN_API_URL,
            headers=self._headers(content_type=True),
            json={"api_type": api_type, **payload},
            timeout=60,
        )
        return _response_data(response, api_type)

    def get(self, api_type, params):
        response = self.session.get(
            OPEN_API_URL,
            headers=self._headers(),
            params={"api_type": api_type, **params},
            timeout=60,
        )
        return _response_data(response, api_type)

    def _headers(self, content_type=False):
        headers = {"Accept": "application/json", "x-api-key": self.api_key}
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers


def _hydrate_product_details(client, records, report):
    spu_ids = sorted({
        str(row.get("spu_id") or "").strip()
        for row in records if row.get("spu_id")
    })
    missing = [spu_id for spu_id in spu_ids if _cached_product(spu_id) is None]
    if missing:
        workers = min(10, len(missing))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(client.product, spu_id): spu_id for spu_id in missing
            }
            completed = 0
            for future in as_completed(futures):
                spu_id = futures[future]
                _store_product(spu_id, future.result())
                completed += 1
                if completed == len(missing) or completed % 25 == 0:
                    report(
                        f"正在补齐商品颜色和尺码：{completed:,}/{len(missing):,}"
                    )
    return [_enrich_record(row, _cached_product(str(row.get("spu_id") or "")))
            for row in records]


def _enrich_record(record, product):
    result = dict(record)
    product = product or {}
    sku = next((
        item for item in product.get("skus") or []
        if str(item.get("id")) == str(record.get("sku_id"))
    ), {})
    attributes = sku.get("attribute_items") or []
    result.update({
        "production_order_id": record.get("order_no"),
        "style_name": product.get("name") or "",
        "blank_product_code": str(record.get("spu_id") or ""),
        "blank_product_name": product.get("name") or "",
        "color": _attribute_name(attributes, 1),
        "size": _attribute_name(attributes, 2),
        "status_name": STATUS_NAMES.get(record.get("status"), record.get("status")),
        "production_batch_code": "",
    })
    return result


def _attribute_name(attributes, attribute_type):
    return next((
        str(item.get("name") or "").strip()
        for item in attributes if item.get("type") == attribute_type
    ), "")


def _response_data(response, api_type):
    try:
        payload = response.json()
    except Exception as error:
        raise HumbirdOpenApiError(
            f"{api_type} 返回了无法识别的响应"
        ) from error
    if response.status_code == 401 or str(payload.get("code")) == "10310005":
        raise HumbirdOpenApiError("蜂鸟开放平台 API Key 无权限或已失效")
    if response.status_code == 429 or str(payload.get("code")) == "10310006":
        raise HumbirdOpenApiError("蜂鸟开放平台接口限流，请稍后重试")
    response.raise_for_status()
    if str(payload.get("code")) != "200":
        raise HumbirdOpenApiError(
            f"{api_type} 网关错误：{payload.get('msg') or payload.get('code')}"
        )
    result = payload.get("result") or {}
    if str(result.get("result_code")) != "200":
        raise HumbirdOpenApiError(
            f"{api_type} 返回错误：{result.get('msg') or result.get('result_code')}"
        )
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _date_range(start_date, end_date, start_hour=0, end_hour=23):
    start_at = datetime.combine(
        start_date, time(hour=int(start_hour)), NEW_YORK
    )
    end_at = datetime.combine(
        end_date,
        time(hour=int(end_hour), minute=59, second=59, microsecond=999999),
        NEW_YORK,
    )
    if (end_date - start_date).days > 29:
        raise ValueError("蜂鸟开放平台单次最多查询 30 天")
    return {
        "from": int(start_at.timestamp() * 1000),
        "to": int(end_at.timestamp() * 1000),
    }


def _deduplicate(rows, field):
    seen, result = set(), []
    for row in rows:
        identity = str(row.get(field) or "").strip()
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        result.append(row)
    return result


def _cached_product(spu_id):
    with _PRODUCT_CACHE_LOCK:
        return _PRODUCT_CACHE.get(spu_id)


def _store_product(spu_id, product):
    with _PRODUCT_CACHE_LOCK:
        _PRODUCT_CACHE[spu_id] = product


# Concise public names for library consumers. The longer names remain public
# so existing applications can migrate without a flag day.
HumbirdClient = HumbirdOpenApiClient
HumbirdApiError = HumbirdOpenApiError
fetch_production_records = fetch_open_production_records
