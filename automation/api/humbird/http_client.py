import hashlib
import hmac
import json
import random
import time

import requests

from automation.api.humbird.payload import build_production_item_payload
from db.automation_credentials import (
    mark_erp_token_error,
    mark_erp_token_used,
    save_erp_token,
)


API_BASE = "https://apigw.hihumbird.com"
PRODUCTION_PATH = "/production/v1/production/order/item/page"
ORDER_DETAILS_PATH = "/oc/v2/orders/list"
REFRESH_PATH = "/uc/v1/users/actions/refresh_token"
PAGE_SIZE = 10000
ORDER_BATCH_SIZE = 200


class HumbirdAuthenticationError(RuntimeError):
    pass


def fetch_humbird_production_records_http(
    platform,
    start_date,
    end_date,
    credentials,
    report_progress=None,
    start_hour=0,
    end_hour=23,
):
    report = report_progress or (lambda _message: None)
    token = str((credentials or {}).get("token") or "").strip()
    if not token:
        raise ValueError(f"{platform} 生产 API 缺少 token")
    session = requests.Session()
    if (credentials or {}).get("token_just_captured"):
        report(f"1/3 正在使用刚捕获的 {platform} token 直接请求 API")
    else:
        report(f"1/3 正在验证 {platform} API token（不打开网页）")
        try:
            refreshed_token = _refresh_token(session, token, platform) or token
        except HumbirdAuthenticationError as error:
            _record_error(credentials, platform, error, expired=True)
            raise
        if refreshed_token != token:
            _persist_refreshed_token(credentials, platform, refreshed_token)
            token = refreshed_token

    records = []
    expected_total = None
    page = 1
    report(f"2/3 正在直接读取 {platform} 生产列表 API")
    while expected_total is None or len(records) < expected_total:
        payload = build_production_item_payload(
            start_date, end_date, page=page, page_size=PAGE_SIZE,
            start_hour=start_hour, end_hour=end_hour,
        )
        body = _json_body(payload)
        response = session.post(
            f"{API_BASE}{PRODUCTION_PATH}",
            data=body,
            headers=_signed_headers("POST", body, token),
            timeout=60,
        )
        try:
            result = _response_data(response, platform)
        except HumbirdAuthenticationError as error:
            _record_error(credentials, platform, error, expired=True)
            raise
        rows = list(result.get("list") or [])
        expected_total = int(result.get("total") or 0)
        records.extend(rows)
        records = _deduplicate(records)
        report(
            f"{platform} API 第 {page} 页："
            f"累计 {len(records):,}/{expected_total:,} 条"
        )
        if not rows or len(records) >= expected_total:
            break
        page += 1
    if len(records) != expected_total:
        raise RuntimeError(
            f"{platform} API 应返回 {expected_total:,} 条，"
            f"实际收到 {len(records):,} 条"
        )
    _record_used(credentials, platform)
    report(f"3/3 {platform} API 读取完成：{len(records):,} 条")
    return records


def fetch_humbird_order_details_http(
    platform,
    order_ids,
    credentials,
    report_progress=None,
    validate_token=True,
):
    """Read order tracking details with the shared database token."""
    report = report_progress or (lambda _message: None)
    token = str((credentials or {}).get("token") or "").strip()
    if not token:
        raise HumbirdAuthenticationError(
            f"{platform} 数据库中没有可用的备用 API token"
        )
    session = requests.Session()
    if validate_token:
        report(f"正在验证 {platform} 数据库备用 token（不打开网页）")
        try:
            refreshed_token = _refresh_token(session, token, platform) or token
        except HumbirdAuthenticationError as error:
            _record_error(credentials, platform, error, expired=True)
            raise
        if refreshed_token != token:
            _persist_refreshed_token(credentials, platform, refreshed_token)
            token = refreshed_token
    else:
        report(f"正在复用本次已验证的 {platform} token 读取订单详情")

    identifiers = list(dict.fromkeys(
        _order_identifier(value)
        for value in order_ids if str(value).strip()
    ))
    details = []
    total_batches = max(
        1, (len(identifiers) + ORDER_BATCH_SIZE - 1) // ORDER_BATCH_SIZE
    )
    for offset in range(0, len(identifiers), ORDER_BATCH_SIZE):
        batch = identifiers[offset:offset + ORDER_BATCH_SIZE]
        body = _json_body({
            "order_ids": batch,
            "query_field_list": ["third_detail"],
        })
        response = session.post(
            f"{API_BASE}{ORDER_DETAILS_PATH}",
            data=body,
            headers=_signed_headers("POST", body, token),
            timeout=60,
        )
        data = _response_data(response, platform, allow_collection=True)
        details.extend(_collection_rows(data))
        current = offset // ORDER_BATCH_SIZE + 1
        report(
            f"备用接口订单详情：{current:,}/{total_batches:,} 批，"
            f"累计 {len(details):,} 个订单"
        )
    _record_used(credentials, platform)
    return details


def _refresh_token(session, token, platform):
    response = session.put(
        f"{API_BASE}{REFRESH_PATH}",
        headers=_signed_headers("PUT", "", token),
        timeout=30,
    )
    data = _response_data(response, platform, allow_scalar=True)
    if isinstance(data, dict):
        return str(
            data.get("token") or data.get("access_token") or ""
        ).strip() or None
    return None


def _persist_refreshed_token(credentials, platform, token):
    if isinstance(credentials, dict):
        credentials["token"] = token
    store = (credentials or {}).get("credential_store")
    secret = (credentials or {}).get("encryption_secret")
    if store is not None and secret:
        try:
            save_erp_token(
                store, platform, token, secret, "automatic-refresh"
            )
        except Exception:
            # A successful ERP request must not fail because audit metadata
            # could not be persisted temporarily.
            pass


def _record_used(credentials, platform):
    store = (credentials or {}).get("credential_store")
    if store is not None:
        try:
            mark_erp_token_used(store, platform)
        except Exception:
            pass


def _record_error(credentials, platform, error, expired=False):
    store = (credentials or {}).get("credential_store")
    if store is not None:
        try:
            mark_erp_token_error(store, platform, error, expired=expired)
        except Exception:
            pass


def _signed_headers(method, body, token):
    stamp = int(time.time() * 1000)
    nonce = random.randint(0, 999998)
    parts = [str(stamp), str(nonce), ""]
    if method.upper() != "GET":
        parts.append(body)
    signature_source = "".join(sorted(parts))
    signature = hmac.new(
        token.encode("utf-8"),
        signature_source.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh_CN",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "nonce": str(nonce),
        "sign": signature,
        "stamp": str(stamp),
    }


def _response_data(
    response, platform, allow_scalar=False, allow_collection=False,
):
    if response.status_code in {401, 403}:
        raise HumbirdAuthenticationError(
            f"{platform} API token 已失效，请重新登录并更新 token"
        )
    response.raise_for_status()
    payload = response.json()
    result_code = str(payload.get("result_code") or "")
    if result_code != "200":
        message = str(payload.get("msg") or "API 返回异常")
        if result_code == "401":
            raise HumbirdAuthenticationError(
                f"{platform} API token 已失效：{message}"
            )
        raise RuntimeError(f"{platform} API 返回错误：{message}")
    data = payload.get("data")
    if allow_scalar or allow_collection:
        return data
    if not isinstance(data, dict):
        raise RuntimeError(f"{platform} API 生产列表格式异常")
    return data


def _collection_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "rows", "orders"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _order_identifier(value):
    text = str(value).strip()
    return int(text) if text.isdigit() else text


def _json_body(payload):
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def _deduplicate(rows):
    seen = set()
    result = []
    for row in rows:
        identity = str(row.get("code") or "").strip()
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        result.append(row)
    return result
