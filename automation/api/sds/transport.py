from urllib.parse import urlparse

import requests


FALLBACK_STATUS_CODES = frozenset({
    404, 405, 408, 425, 429, 500, 502, 503, 504,
})


def request_with_sds_fallback(
    client,
    method,
    urls,
    *,
    report_progress=None,
    operation="SDS接口",
    **kwargs,
):
    candidates = tuple(urls)
    if not candidates:
        raise ValueError("SDS接口地址不能为空")

    report = report_progress or (lambda _message: None)
    request = getattr(client, method.lower())
    for index, url in enumerate(candidates):
        has_fallback = index + 1 < len(candidates)
        try:
            response = request(url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as error:
            if not has_fallback:
                raise
            _report_fallback(report, operation, url, candidates[index + 1], error)
            continue

        if has_fallback and response.status_code in FALLBACK_STATUS_CODES:
            _report_fallback(
                report,
                operation,
                url,
                candidates[index + 1],
                response.status_code,
            )
            continue

        response.raise_for_status()
        return response

    raise RuntimeError(f"{operation}没有可用入口")


def _report_fallback(report, operation, failed_url, adopted_url, reason):
    failed_host = urlparse(failed_url).netloc
    adopted_host = urlparse(adopted_url).netloc
    if isinstance(reason, requests.Timeout):
        detail = "连接超时"
    elif isinstance(reason, requests.ConnectionError):
        detail = "连接失败"
    else:
        detail = f"HTTP {reason}"
    report(
        f"{operation}：首选入口 {failed_host} {detail}；"
        f"已切换到 {adopted_host}，本次任务继续。"
    )
