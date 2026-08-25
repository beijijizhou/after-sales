from datetime import datetime, time
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
PAGE_SIZE = 5000


def build_production_item_payload(
    start_date,
    end_date,
    page=1,
    page_size=PAGE_SIZE,
    start_hour=0,
    end_hour=23,
):
    start_at = datetime.combine(
        start_date, time(hour=int(start_hour)), NEW_YORK
    )
    end_at = datetime.combine(
        end_date,
        time(hour=int(end_hour), minute=59, second=59, microsecond=999999),
        NEW_YORK,
    )
    return {
        "page": page,
        "page_size": page_size,
        "sum_total_qty": True,
        "status": [],
        "order_compositions": [],
        "process_route_ids": [],
        "order_third_status_list": [],
        "performance_status_list": [],
        "system_performance_status_list": [],
        "shipping_status_list": [],
        "order_source_list": [],
        "logistics_sorting_code_list": [],
        "begin_production_time": {
            "from": str(int(start_at.timestamp() * 1000)),
            "to": str(int(end_at.timestamp() * 1000)),
        },
        "styles": {"style_sku_ids": []},
        "sort": [{"sort_by": "created", "sort_type": 2}],
    }
