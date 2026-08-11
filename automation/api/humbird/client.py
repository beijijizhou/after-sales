"""Backward-compatible Humbird entrypoint that never starts a browser.

Production reads must work in server environments such as Streamlit Cloud.
The browser login flow is intentionally isolated in ``local_auth.py`` and is
only used by an administrator to refresh a fully expired authorization.
"""

from automation.api.humbird.http_client import (
    fetch_humbird_production_records_http,
)


def fetch_humbird_production_records(
    platform,
    start_date,
    end_date,
    report_progress=None,
    credentials=None,
):
    if not credentials or not str(credentials.get("token") or "").strip():
        raise ValueError(
            f"{platform} 未提供共享 API token；"
            "服务器不会启动 Chrome，请检查数据库 ERP 授权"
        )
    return fetch_humbird_production_records_http(
        platform,
        start_date,
        end_date,
        credentials,
        report_progress,
    )


def _normalize_api_result(response):
    current = response
    for _ in range(5):
        if not isinstance(current, dict):
            break
        if "list" in current and "total" in current:
            return current
        nested = next(
            (
                current.get(key)
                for key in ("data", "result", "body")
                if isinstance(current.get(key), dict)
            ),
            None,
        )
        if nested is None:
            break
        current = nested
    raise RuntimeError("生产接口响应中没有 list / total")


def _deduplicate_rows(rows):
    result = []
    seen_codes = set()
    for row in rows:
        code = row.get("code") if isinstance(row, dict) else None
        if code not in (None, ""):
            marker = str(code)
            if marker in seen_codes:
                continue
            seen_codes.add(marker)
        result.append(row)
    return result
