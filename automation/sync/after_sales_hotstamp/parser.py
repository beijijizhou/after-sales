"""Normalize one weekly hotstamp-film workbook into auditable source rows."""

from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import re

from utils.production.normalization import normalize_platform


WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEK_TITLE = re.compile(
    r"^(?P<start_month>\d{2})/(?P<start_day>\d{2})-"
    r"(?P<end_month>\d{2})/(?P<end_day>\d{2})$"
)
PLATFORM_ALIASES = {
    "7创": "七创",
    "sds-1": "SDS1",
    "sds1": "SDS1",
    "sds-2": "SDS2",
    "sds2": "SDS2",
    "pt莆田": "莆田",
}


def is_weekly_workbook(title):
    return bool(WEEK_TITLE.fullmatch(str(title or "").strip()))


def parse_week_start(title, created_time):
    match = WEEK_TITLE.fullmatch(str(title or "").strip())
    if not match:
        raise ValueError(f"不是周表名称：{title}")
    created_year = _created_year(created_time)
    start_month = int(match.group("start_month"))
    start_day = int(match.group("start_day"))
    return date(created_year, start_month, start_day)


def parse_daily_rows(values, source, sheet_name, business_date):
    if not values:
        return [], []
    header = [_text(value) for value in values[0]]
    modern = len(header) > 3 and header[2] == "配衣" and header[3] == "数量"
    rows = []
    invalid = []
    for row_number, values_row in enumerate(values[1:], start=2):
        cells = list(values_row) + [None] * 9
        record = _modern_record(cells) if modern else _legacy_record(cells)
        if not _has_business_input(record):
            continue
        record.update({
            "source_file_id": source["id"],
            "source_file_name": source["name"],
            "source_sheet_name": sheet_name,
            "source_row_number": row_number,
            "business_date": business_date.isoformat(),
        })
        if not record["source_platform"] or record["film_quantity"] is None:
            record["validation_error"] = "平台或数量为空"
            invalid.append(record)
            continue
        if record["film_quantity"] < 0:
            record["validation_error"] = "数量不能为负数"
            invalid.append(record)
            continue
        rows.append(record)
    return rows, invalid


def normalize_source_platform(value):
    source = _text(value)
    if not source:
        return "未标记平台"
    normalized = normalize_platform(source)
    return PLATFORM_ALIASES.get(normalized, PLATFORM_ALIASES.get(
        normalized.lower(), normalized
    ))


def fingerprint_rows(rows):
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _modern_record(cells):
    return {
        "source_platform": _text(cells[0]),
        "platform": normalize_source_platform(cells[0]),
        "cutting_person": _text(cells[1]),
        "matching_person": _text(cells[2]),
        "film_quantity": _integer(cells[3]),
        "is_hoodie": _boolean(cells[4]),
        "multi_press_count": _integer(cells[5]),
        "is_white_board": _boolean(cells[6]),
        "hotstamp_person": _text(cells[7]),
        "qa_person": _text(cells[8]),
    }


def _legacy_record(cells):
    return {
        "source_platform": _text(cells[0]),
        "platform": normalize_source_platform(cells[0]),
        "cutting_person": _text(cells[1]),
        "matching_person": "",
        "film_quantity": _integer(cells[2]),
        "is_hoodie": _boolean(cells[3]),
        "multi_press_count": _integer(cells[4]),
        "is_white_board": False,
        "hotstamp_person": _text(cells[5]),
        "qa_person": _text(cells[6]),
    }


def _has_business_input(record):
    fields = (
        "source_platform", "cutting_person", "matching_person",
        "film_quantity", "hotstamp_person", "qa_person",
    )
    return any(record.get(field) not in (None, "") for field in fields)


def _created_year(value):
    if not value:
        return datetime.now().year
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).year


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _integer(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _boolean(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "是"}
