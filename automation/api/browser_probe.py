import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import (
    CDP_URL,
    connect_debug_chrome,
    find_erp_page,
)


OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / ".cache"
    / "erp_api_probe"
)
SENSITIVE_HEADERS = {
    "authorization", "cookie", "proxy-authorization",
    "set-cookie", "x-auth-token", "access-token",
}
IGNORED_HOST_PARTS = {
    "qiyukf.com", "google-analytics.com", "doubleclick.net",
    "sentry.io",
}


def probe_page_api(host, path_contains, output_name):
    records = []
    with sync_playwright() as playwright:
        browser = connect_debug_chrome(
            playwright, f"https://{host}"
        )
        page = find_erp_page(browser, host)
        candidates = [
            item
            for context in browser.contexts
            for item in context.pages
            if host in item.url and path_contains in item.url
        ]
        if candidates:
            page = candidates[-1]

        def record_response(response):
            request = response.request
            parsed = urlparse(request.url)
            if request.resource_type not in {"xhr", "fetch"}:
                return
            if any(
                ignored in parsed.netloc
                for ignored in IGNORED_HOST_PARTS
            ):
                return
            item = {
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "request_headers": sorted(
                    name for name in request.headers
                    if name.casefold() not in SENSITIVE_HEADERS
                ),
                "post_data": _parse_post_data(request.post_data),
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
            item["response_shape"] = _response_shape(response)
            records.append(item)

        page.on("response", record_response)
        page.reload(wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8_000)
        browser.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT_DIR / f"{output_name}.json"
    destination.write_text(
        json.dumps({
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "host": host,
            "page_path": path_contains,
            "requests": records,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination, records


def _parse_post_data(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value[:5000]


def _response_shape(response):
    content_type = response.headers.get("content-type", "").casefold()
    if "json" not in content_type:
        return {"type": content_type or "unknown"}
    try:
        payload = response.json()
    except Exception:
        return {"type": "invalid-json"}
    return _describe(payload)


def _describe(value, depth=0):
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {
            key: _describe(item, depth + 1)
            for key, item in list(value.items())[:30]
        }
    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
            "item": _describe(value[0], depth + 1) if value else None,
        }
    return type(value).__name__


def main():
    parser = argparse.ArgumentParser(
        description="被动记录已登录 ERP 页面的一次 API 请求结构。"
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--name", required=True)
    arguments = parser.parse_args()
    destination, records = probe_page_api(
        arguments.host, arguments.path, arguments.name
    )
    print(f"已记录 {len(records)} 个接口：{destination}")
    for item in records:
        print(f"{item['method']} {item['url']} [{item['status']}]")


if __name__ == "__main__":
    main()
