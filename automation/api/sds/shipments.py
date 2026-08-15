import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from automation.api.sds.auth import USER_AGENT, login_sds_factory
from automation.integrations.stages import UNACCEPTED, stage_label


ORDERS_URL = "https://factory-api.sdspod.com/factory_orders/v2/order/allByEs"
QA_LOGIN_URL = "https://g-pod-api.sdspod.com/pod/auth/login"
PARCEL_URL = "https://pod-api.sdspod.com/pod/parcel/qc/{order_id}/detail"


def fetch_sds_pending_shipments(
    profile,
    account,
    max_pages=5,
    status=UNACCEPTED,
    time_range=None,
    platform_name=None,
    department="DTF",
):
    client, token, _factory_id = login_sds_factory(account["factory"])
    records = _fetch_order_records(
        client, token, max_pages, status=status, time_range=time_range
    )
    qa_token = _login_qa(client, account["qa"])
    rows = _fetch_parcels(
        client,
        qa_token,
        records,
        profile,
        platform_name or profile,
        department,
    )
    for row in rows:
        row["local_acceptance_status"] = stage_label(status)
    return rows


def _fetch_order_records(
    client, token, max_pages, status=UNACCEPTED, time_range=None,
):
    rows = []
    headers = {"access-token": token, "User-Agent": USER_AGENT}
    for page in range(1, max_pages + 1):
        params = {
            "page": page, "size": 500, "status": status,
            "noManuscriptFeedbackStatus": 1, "sort": "-id",
        }
        params.update(time_range or {})
        response = client.get(
            ORDERS_URL,
            params=params,
            headers=headers, timeout=60,
        )
        response.raise_for_status()
        page_rows = response.json().get("records", [])
        rows.extend(page_rows)
        if len(page_rows) < 500:
            break
    return rows


def _login_qa(client, credentials):
    required = ("extraInfo", "no", "password", "username")
    missing = [key for key in required if not credentials.get(key)]
    if missing:
        raise ValueError(f"SDS QA配置缺少：{', '.join(missing)}")
    response = client.post(
        QA_LOGIN_URL,
        params={"t": int(time.time() * 1000)},
        json={key: credentials[key] for key in required},
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = _qa_token(payload)
    if not token:
        raise ValueError("SDS QA登录成功，但没有返回token")
    return token


def _qa_token(payload):
    data = payload.get("data") or {}
    return (
        payload.get("token")
        or payload.get("accessToken")
        or data.get("token")
        or data.get("accessToken")
        or data.get("access_token")
    )


def _fetch_parcels(
    client, qa_token, records, profile, platform_name, department
):
    headers = {"access-token": qa_token, "User-Agent": USER_AGENT}
    results = []
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(records)))) as pool:
        futures = {
            pool.submit(
                _parcel_rows,
                client,
                headers,
                record,
                profile,
                platform_name,
                department,
            ): record
            for record in records if _order_id(record)
        }
        for future in as_completed(futures):
            results.extend(future.result())
    return results


def _parcel_rows(
    client, headers, record, profile, platform_name=None, department="DTF"
):
    response = client.get(
        PARCEL_URL.format(order_id=_order_id(record)),
        params={"t": int(time.time() * 1000)}, headers=headers, timeout=(5, 30),
    )
    response.raise_for_status()
    rows = []
    for parcel in response.json().get("detailList", []):
        tracking = str(parcel.get("carriageNo") or "").strip()
        if not tracking:
            continue
        rows.append({
            "tenant_code": "default",
            "erp_platform": platform_name or profile,
            "erp_account": profile,
            "department": department,
            "external_order_id": str(record.get("no") or ""),
            "merchant_order_id": str(record.get("merchantOrderNo") or ""),
            "tracking_number": tracking,
            "carrier": str(parcel.get("carriageName") or ""),
            "erp_status": str(record.get("status") or ""),
            "label_url": parcel.get("pdfUrl"),
            "backup_label_url": parcel.get("laberPdf"),
            "local_acceptance_status": "未接单",
            "source_payload": {"record": record, "parcel": parcel},
        })
    return rows


def _order_id(record):
    order = record.get("order") or {}
    return str(order.get("id") or record.get("orderId") or "").strip()
