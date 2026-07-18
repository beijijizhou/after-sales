import json
import re

from utils.erp.time_range import build_hour_range

from automation.api.diy19.auth import USER_AGENT, login_diy19


DIY19_BASE_URLS = {
    "七创": "http://us.qcpod.19diy.com",
    "一朵云": "http://usf.19diy.com",
}
TEMPLATE_PATTERN = re.compile(
    r'ProductTemplateID:\s*"([^"]+)"\s*,\s*'
    r'ProductTemplateID_SubKey:\s*"([^"]*)"'
)


def fetch_diy19_production_summary(
    platform,
    start_date,
    end_date,
    credentials,
    report_progress=None,
    start_hour=0,
    end_hour=23,
):
    report = report_progress or (lambda _message: None)
    base_url = DIY19_BASE_URLS[platform]
    report(f"1/4 正在登录{platform}工厂接口")
    client = login_diy19(base_url, platform, credentials)
    headers = _request_headers(base_url)

    report(f"2/4 正在读取{platform}商品模板")
    page = client.get(
        f"{base_url}/ProduceOrderProduct/IndexForOrder?lang=zh_chs",
        headers=headers,
        timeout=30,
    )
    page.raise_for_status()
    templates = dict(TEMPLATE_PATTERN.findall(page.text))

    report(f"3/4 正在获取{platform}生产汇总（单次请求）")
    response = client.post(
        f"{base_url}/ProduceOrderProduct/ListForTemplate?lang=zh_chs",
        data=_summary_form(
            start_date, end_date, start_hour, end_hour
        ),
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("Code") != 200:
        raise ValueError(payload.get("Message") or f"{platform}数据获取失败")
    records = json.loads(payload.get("Data") or "[]")
    for record in records:
        template_id = str(record.get("ProductTemplateID") or "")
        record["ProductTemplateName"] = templates.get(
            template_id,
            f"未知模板 {template_id}",
        )
        record["StartDate"] = start_date.isoformat()
        record["EndDate"] = end_date.isoformat()
    report(f"4/4 {platform}数据接收完成：{len(records):,} 个模板组合")
    return records


def _summary_form(start_date, end_date, start_hour=0, end_hour=23):
    start_at, end_at = build_hour_range(
        start_date, end_date, start_hour, end_hour
    )
    return {
        "PageIndex": "1", "PageSize": "2000",
        "QueryItems[0][FieldName]": "SYS_DATE_ADD",
        "QueryItems[0][Comparator]": ">=",
        "QueryItems[0][FieldValue]": start_at.strftime("%Y/%m/%d %H:%M:%S"),
        "QueryItems[1][FieldName]": "SYS_DATE_ADD",
        "QueryItems[1][Comparator]": "<=",
        "QueryItems[1][FieldValue]": end_at.strftime("%Y/%m/%d %H:%M:%S"),
        "SortItems[0][FieldName]": "SYS_DATE_ADD",
        "SortItems[0][SortSymbol]": "ASC",
    }


def _request_headers(base_url):
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": base_url,
        "Referer": f"{base_url}/ProduceOrderProduct/IndexForOrder?lang=zh_chs",
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }
