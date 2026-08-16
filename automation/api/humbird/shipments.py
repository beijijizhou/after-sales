"""Humbird Open Platform shipment adapter."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time

from automation.api.humbird.http_client import (
    HumbirdAuthenticationError,
    ORDER_BATCH_SIZE,
    fetch_humbird_order_details_http,
    fetch_humbird_production_records_http,
)
from automation.api.humbird.open_client import (
    HumbirdOpenApiClient,
    HumbirdOpenApiError,
)
from automation.integrations.stages import (
    IN_PRODUCTION,
    SHIPPED,
    UNACCEPTED,
    stage_label,
)


HUMBIRD_OPEN_LOGISTICS_PLATFORMS = frozenset({"Haloo", "隆丰"})
HUMBIRD_TOKEN_LOGISTICS_PLATFORMS = frozenset({"莆田"})
HUMBIRD_LOGISTICS_PLATFORMS = (
    HUMBIRD_OPEN_LOGISTICS_PLATFORMS
    | HUMBIRD_TOKEN_LOGISTICS_PLATFORMS
)
OFFICIAL_BACKOFF_SECONDS = 600
_OFFICIAL_BACKOFF_UNTIL = {}
_OFFICIAL_BACKOFF_LOCK = Lock()


STATUS_QUERIES_BY_STAGE = {
    UNACCEPTED: ((-1,),),
    IN_PRODUCTION: ((1, 5),),
    SHIPPED: ((9,),),
}


class HumbirdBrowserRefreshRequired(HumbirdAuthenticationError):
    """The official and shared-token routes cannot complete the read."""


def fetch_humbird_shipments_with_fallback(
    platform,
    credentials,
    start_date,
    end_date,
    status=1,
    department="DTF",
    report_progress=None,
):
    """Use official API first, then the database-token API route."""
    report = report_progress or (lambda _message: None)
    official_error = None
    api_key = str((credentials or {}).get("api_key") or "").strip()
    backoff_seconds = _official_backoff_remaining(platform)
    if api_key and backoff_seconds <= 0:
        report("第1级：正在使用蜂鸟官方开放 API。")
        try:
            return fetch_humbird_shipments(
                platform,
                credentials,
                start_date,
                end_date,
                status=status,
                department=department,
                report_progress=report_progress,
            )
        except Exception as error:
            official_error = error
            if _is_rate_limit(error):
                _start_official_backoff(platform)
            report(
                f"官方 API 不可用（{error}）；"
                "第2级：切换数据库中的共享 token。"
            )
    elif api_key:
        report(
            f"官方 API 刚发生限流，剩余约 {backoff_seconds // 60 + 1} 分钟"
            "不再重复请求；第2级：直接读取数据库共享 token。"
        )
    else:
        report("未配置官方 API Key；第2级：读取数据库共享 token。")

    if not str((credentials or {}).get("token") or "").strip():
        reason = f"；官方 API 原因：{official_error}" if official_error else ""
        raise HumbirdBrowserRefreshRequired(
            f"{platform} 数据库中没有可用 token{reason}"
        )
    try:
        return fetch_humbird_shipments_legacy(
            platform,
            credentials,
            start_date,
            end_date,
            status=status,
            department=department,
            report_progress=report_progress,
        )
    except HumbirdAuthenticationError as error:
        raise HumbirdBrowserRefreshRequired(str(error)) from error


def fetch_humbird_shipments_legacy(
    platform,
    credentials,
    start_date,
    end_date,
    status=1,
    department="DTF",
    report_progress=None,
):
    """Read tracking relationships through the signed legacy endpoints."""
    report = report_progress or (lambda _message: None)
    report("数据库 token 已读取，正在直接请求备用 API（无需浏览器）。")
    items = fetch_humbird_production_records_http(
        platform,
        start_date,
        end_date,
        credentials,
        report_progress,
    )
    items = _filter_stage_items(items, status)
    orders = _group_legacy_orders(items)
    report(
        f"备用 API 已取得 {len(items):,} 个生产项目；"
        f"正在读取 {len(orders):,} 个订单的物流详情。"
    )
    order_ids = list(orders)
    sample_ids = order_ids[:ORDER_BATCH_SIZE]
    report(
        f"备用 API 正在抽样验证物流字段："
        f"{len(sample_ids):,}/{len(order_ids):,} 个订单。"
    )
    details = fetch_humbird_order_details_http(
        platform,
        sample_ids,
        credentials,
        report_progress,
        validate_token=False,
    )
    if not details:
        raise RuntimeError(
            f"{platform} 备用API没有返回订单详情，不能判定为0条物流"
        )
    if not any(_tracking_field_available(detail) for detail in details):
        raise RuntimeError(
            f"{platform} 备用API订单详情未返回物流号字段；"
            "已停止后续读取，不能判定为0条物流"
        )
    if len(sample_ids) < len(order_ids):
        details.extend(fetch_humbird_order_details_http(
            platform,
            order_ids[len(sample_ids):],
            credentials,
            report_progress,
            validate_token=False,
        ))
    detail_map = _map_order_details(details)
    rows = []
    for position, (order_id, order_items) in enumerate(orders.items()):
        detail = detail_map.get(str(order_id))
        if detail is None and position < len(details):
            detail = details[position]
        if not detail:
            continue
        first = order_items[0]
        for tracking in _tracking_entries(detail):
            tracking_number = _tracking_number(tracking)
            if not tracking_number:
                continue
            rows.append({
                "tenant_code": "default",
                "erp_platform": platform,
                "erp_account": platform,
                "department": department,
                "external_order_id": str(
                    first.get("order_no")
                    or detail.get("order_no")
                    or detail.get("code")
                    or order_id
                ),
                "merchant_order_id": str(
                    first.get("order_third_id")
                    or detail.get("order_third_id")
                    or ""
                ),
                "tracking_number": tracking_number,
                "carrier": _carrier_name(tracking, detail),
                "erp_status": _erp_status(order_items),
                "label_url": _label_url(tracking, detail),
                "backup_label_url": None,
                "local_acceptance_status": stage_label(status),
                "source_payload": {
                    "provider": "Humbird database-token API",
                    "delivery_time": first.get("delivery_time"),
                    "order_detail": detail,
                    "production_item_codes": [
                        item.get("code") for item in order_items
                    ],
                },
            })
    report(f"数据库 token 备用通道完成：{len(rows):,} 条物流关系。")
    return sorted(rows, key=lambda row: row["external_order_id"])


def fetch_humbird_shipments(
    platform,
    credentials,
    start_date,
    end_date,
    status=1,
    department="DTF",
    report_progress=None,
):
    report = report_progress or (lambda _message: None)
    client = HumbirdOpenApiClient(credentials)
    items = _stage_items(client, start_date, end_date, status)
    report(f"已取得 {len(items):,} 个生产项目，正在整理订单...")
    orders = _group_orders(items)
    report(f"需要读取 {len(orders):,} 个订单的面单信息。")
    rows = []
    pool = ThreadPoolExecutor(max_workers=min(4, max(1, len(orders))))
    try:
        futures = {
            pool.submit(client.waybill, order_no): (order_no, order_items)
            for order_no, order_items in orders.items()
        }
        interval = max(1, len(futures) // 10)
        for completed, future in enumerate(as_completed(futures), start=1):
            order_no, order_items = futures[future]
            if completed == len(futures) or completed % interval == 0:
                report(f"面单获取进度：{completed:,}/{len(futures):,}。")
            try:
                waybill = future.result()
            except Exception as error:
                if "不存在" in str(error) or "404" in str(error):
                    continue
                for pending in futures:
                    pending.cancel()
                raise
            tracking = str(waybill.get("track_number") or "").strip()
            if not tracking:
                continue
            first = order_items[0]
            rows.append({
                "tenant_code": "default",
                "erp_platform": platform,
                "erp_account": platform,
                "department": department,
                "external_order_id": order_no,
                "merchant_order_id": str(first.get("order_third_id") or ""),
                "tracking_number": tracking,
                "carrier": str(waybill.get("logistics_method_name") or ""),
                "erp_status": _erp_status(order_items),
                "label_url": waybill.get("url"),
                "backup_label_url": None,
                "local_acceptance_status": stage_label(status),
                "source_payload": {
                    "provider": "Humbird Open Platform",
                    "delivery_time": first.get("delivery_time"),
                    "waybill": waybill,
                    "production_item_codes": [
                        item.get("code") for item in order_items
                    ],
                },
            })
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return sorted(rows, key=lambda row: row["external_order_id"])


def _stage_items(client, start_date, end_date, stage):
    items = []
    for statuses in STATUS_QUERIES_BY_STAGE.get(stage, (None,)):
        items.extend(client.production_items(
            start_date, end_date, statuses=statuses
        ))
    deduplicated = {str(item.get("code") or id(item)): item for item in items}
    return list(deduplicated.values())


def _filter_stage_items(items, stage):
    if stage == UNACCEPTED:
        return [item for item in items if _status_value(item) == -1]
    if stage == IN_PRODUCTION:
        return [
            item for item in items
            if _status_value(item) in {1, 5}
        ]
    if stage == SHIPPED:
        return [item for item in items if _status_value(item) == 9]
    return list(items)


def _status_value(item):
    try:
        return int(item.get("status"))
    except (TypeError, ValueError):
        return None


def _group_orders(items):
    result = {}
    for item in items:
        order_no = str(item.get("order_no") or "").strip()
        if order_no:
            result.setdefault(order_no, []).append(item)
    return result


def _group_legacy_orders(items):
    result = {}
    for item in items:
        order_id = str(item.get("rel_id") or item.get("order_no") or "").strip()
        if order_id:
            result.setdefault(order_id, []).append(item)
    return result


def _map_order_details(details):
    result = {}
    for detail in details:
        for key in ("id", "order_id", "rel_id", "order_no", "code"):
            value = str(detail.get(key) or "").strip()
            if value:
                result[value] = detail
    return result


def _tracking_entries(detail):
    third = detail.get("third_detail") or {}
    entries = (
        third.get("track_number_list")
        or detail.get("track_number_list")
        or []
    )
    if isinstance(entries, (str, int)):
        return [entries]
    return list(entries) if isinstance(entries, list) else []


def _tracking_field_available(detail):
    third = detail.get("third_detail") or {}
    return (
        isinstance(third, dict) and "track_number_list" in third
    ) or "track_number_list" in detail


def _tracking_number(entry):
    if isinstance(entry, (str, int)):
        return str(entry).strip()
    if not isinstance(entry, dict):
        return ""
    return str(
        entry.get("track_number")
        or entry.get("tracking_number")
        or entry.get("tracking_no")
        or entry.get("number")
        or entry.get("code")
        or ""
    ).strip()


def _carrier_name(entry, detail):
    entry = entry if isinstance(entry, dict) else {}
    third = detail.get("third_detail") or {}
    return str(
        entry.get("logistics_method_name")
        or entry.get("carrier")
        or entry.get("logistics_name")
        or third.get("logistics_method_name")
        or third.get("logistics_name")
        or detail.get("logistics_method_name")
        or ""
    ).strip()


def _label_url(entry, detail):
    entry = entry if isinstance(entry, dict) else {}
    third = detail.get("third_detail") or {}
    return next((
        value for value in (
            entry.get("url"),
            entry.get("label_url"),
            entry.get("pdf_url"),
            entry.get("waybill_url"),
            entry.get("logistics_label"),
            third.get("label_url"),
            third.get("pdf_url"),
            third.get("waybill_url"),
            third.get("logistics_label"),
            detail.get("label_url"),
            detail.get("pdf_url"),
            detail.get("waybill_url"),
            detail.get("logistics_label"),
        ) if value
    ), None)


def _erp_status(items):
    statuses = {_status_value(item) for item in items}
    if 9 in statuses:
        return "已生产/已发货"
    if statuses & {1, 5}:
        return "已接单/生产中"
    if -1 in statuses:
        return "未接单"
    return ",".join(sorted(str(value) for value in statuses if value is not None))


def _is_rate_limit(error):
    return isinstance(error, HumbirdOpenApiError) and "限流" in str(error)


def _start_official_backoff(platform):
    with _OFFICIAL_BACKOFF_LOCK:
        _OFFICIAL_BACKOFF_UNTIL[platform] = (
            time.monotonic() + OFFICIAL_BACKOFF_SECONDS
        )


def _official_backoff_remaining(platform):
    with _OFFICIAL_BACKOFF_LOCK:
        remaining = _OFFICIAL_BACKOFF_UNTIL.get(platform, 0) - time.monotonic()
    return max(0, int(remaining))
