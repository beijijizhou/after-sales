from dataclasses import dataclass


ENTRY_MANUAL = "人工登记"
ENTRY_SYSTEM = "系统读取"


@dataclass(frozen=True)
class DailyConsumptionFlow:
    code: str
    label: str
    department: str
    category: str
    entry_source: str
    model_source: str
    ledger: str


DAILY_CONSUMPTION_FLOWS = {
    "dtf_consumables": DailyConsumptionFlow(
        "dtf_consumables", "DTF 耗材", "DTF", "耗材",
        ENTRY_MANUAL, "人工耗材领用", "耗材库存流水",
    ),
    "black_white_tshirts": DailyConsumptionFlow(
        "black_white_tshirts", "黑白短袖", "DTF", "黑白短袖",
        ENTRY_MANUAL, "仓库每日出货", "生产库存流水",
    ),
    "colored_tshirts": DailyConsumptionFlow(
        "colored_tshirts", "彩色短袖", "DTF", "彩色短袖",
        ENTRY_SYSTEM, "生产系统数据", "生产库存流水",
    ),
    "uv_production": DailyConsumptionFlow(
        "uv_production", "UV 生产库存", "UV", "*",
        ENTRY_SYSTEM, "Google Sheets", "生产库存流水",
    ),
}


MANUAL_INVENTORY_REASONS = {
    "仓库每日出货", "每日正常出货", "每日出货", "黑白短袖出库",
}
COLORED_REASON_PREFIX = "彩色短袖生产自动扣减"
UV_REASON_PREFIX = "Google Sheets UV每日消耗"


def inventory_daily_consumption_flow(department, category):
    department = str(department or "").strip().upper()
    category = str(category or "").strip()
    if department == "DTF" and category == "黑白短袖":
        return DAILY_CONSUMPTION_FLOWS["black_white_tshirts"]
    if department == "DTF" and category == "彩色短袖":
        return DAILY_CONSUMPTION_FLOWS["colored_tshirts"]
    if department == "UV":
        return DAILY_CONSUMPTION_FLOWS["uv_production"]
    return None


def daily_consumption_source(reason):
    value = str(reason or "").strip()
    if value.startswith("撤销："):
        value = value.removeprefix("撤销：").strip()
    parts = [part.strip() for part in value.split("；") if part.strip()]
    if any(part in MANUAL_INVENTORY_REASONS for part in parts):
        return ENTRY_MANUAL
    if any(
        part.startswith((COLORED_REASON_PREFIX, UV_REASON_PREFIX))
        for part in parts
    ):
        return ENTRY_SYSTEM
    return ""


def is_daily_consumption_reason(reason):
    return bool(daily_consumption_source(reason))
