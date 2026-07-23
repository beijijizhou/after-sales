from datetime import datetime


WEEKDAY_NAMES = [
    "星期一", "星期二", "星期三", "星期四",
    "星期五", "星期六", "星期日",
]
WEEKDAY_SHORT_NAMES = [
    "周一", "周二", "周三", "周四", "周五", "周六", "周日",
]


def format_date_with_weekday(value):
    day = normalize_date(value)
    return f"{day.isoformat()} {WEEKDAY_NAMES[day.weekday()]}"


def format_chart_date(value):
    day = normalize_date(value)
    return f"{day.strftime('%m/%d')} {WEEKDAY_SHORT_NAMES[day.weekday()]}"


def normalize_date(value):
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "date"):
        return value.date()
    return value
