"""Pure daily inventory-completion models."""

from datetime import date, timedelta

import pandas as pd

from utils.daily_consumption import COLORED_REASON_PREFIX, UV_REASON_PREFIX


DAILY_FLOW_LABELS = {
    "black_white": "黑白短袖", "consumables": "DTF 耗材",
    "colored": "彩色短袖", "uv": "UV 生产库存",
}
DAILY_COMPLETION_START_DATE = date(2026, 8, 1)


def build_daily_completion_dates(movements, consumable_batches):
    active = active_inventory_movements(movements)
    reasons = active.get("reason", pd.Series(index=active.index, dtype=str)).fillna("").astype(str)
    quantities = pd.to_numeric(active.get("quantity_change", 0), errors="coerce").fillna(0)
    dates = pd.to_datetime(active.get("movement_date"), errors="coerce").dt.date
    department = active.get("department", pd.Series(index=active.index, dtype=str)).fillna("").astype(str)
    category = active.get("category", pd.Series(index=active.index, dtype=str)).fillna("").astype(str)
    outbound = quantities.lt(0) & dates.notna()
    colored_reason = COLORED_REASON_PREFIX + " " + dates.astype(str)
    return {
        "black_white": set(dates[
            outbound & department.eq("DTF") & category.eq("黑白短袖")
            & reasons.isin({"仓库每日出货", "每日正常出货", "每日出货", "黑白短袖出库"})
        ]),
        "colored": set(dates[
            outbound & department.eq("DTF") & category.eq("彩色短袖")
            & reasons.str.split("｜").str[0].eq(colored_reason)
        ]),
        "uv": set(dates[
            outbound & department.eq("UV") & reasons.str.startswith(UV_REASON_PREFIX)
        ]),
        "consumables": active_consumable_issue_dates(consumable_batches),
    }


def build_daily_completion_table(completed, start_date, end_date):
    expected = {
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    }
    rows = []
    for code, label in DAILY_FLOW_LABELS.items():
        recorded = set(completed.get(code, set())) & expected
        missing = sorted(expected - recorded)
        automatic = code in {"colored", "uv"}
        rows.append({
            "出库项目": label, "数据方式": "系统读取" if automatic else "人工登记",
            "已完成天数": len(recorded), "检查天数": len(expected),
            "待处理天数": len(missing),
            "待处理日期": "、".join(value.strftime("%m/%d") for value in missing) or "无",
            "处理方式": "读取来源并扣减" if automatic else "补录实际出库",
        })
    return pd.DataFrame(rows)


def build_automatic_missing_dates(completed, start_date, end_date):
    expected = {
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    }
    labels = {code: DAILY_FLOW_LABELS[code] for code in ["colored", "uv"]}
    result = {}
    for movement_date in sorted(expected, reverse=True):
        missing = [
            label for code, label in labels.items()
            if movement_date not in set(completed.get(code, set()))
        ]
        if missing:
            result[movement_date] = "、".join(missing)
    return result


def build_today_completion_status(completed, today):
    completed_labels, pending_labels = [], []
    for code, label in DAILY_FLOW_LABELS.items():
        (completed_labels if today in set(completed.get(code, set())) else pending_labels).append(label)
    return {"date": today, "completed": completed_labels, "pending": pending_labels}


def build_today_completion_table(completed, today):
    rows = []
    for code, label in DAILY_FLOW_LABELS.items():
        automatic = code in {"colored", "uv"}
        done = today in set(completed.get(code, set()))
        next_step = "无需处理" if done else (
            "今日结束后由系统读取" if automatic else "今日结束后补录实际出库"
        )
        rows.append({
            "出库项目": label, "数据方式": "系统读取" if automatic else "人工登记",
            "今日状态": "已完成" if done else "进行中", "计入补录": "否",
            "下一步": next_step,
        })
    return pd.DataFrame(rows)


def active_inventory_movements(movements):
    if movements is None or movements.empty:
        return pd.DataFrame(columns=[
            "department", "category", "movement_date", "quantity_change",
            "reason", "batch_id", "reversal_of_batch_id",
        ])
    result = movements.copy()
    reversed_ids = set(result.get("reversal_of_batch_id", pd.Series(dtype=str)).dropna().astype(str))
    if "reversal_of_batch_id" in result:
        result = result[result["reversal_of_batch_id"].isna()]
    if "batch_id" in result and reversed_ids:
        result = result[~result["batch_id"].astype(str).isin(reversed_ids)]
    return result


def active_consumable_issue_dates(batches):
    if batches is None or batches.empty:
        return set()
    result = batches.copy()
    reversed_ids = set(result.get("reversal_of_batch_id", pd.Series(dtype=str)).dropna().astype(str))
    source_names = result.get(
        "source_file_name", pd.Series(index=result.index, dtype=str)
    ).fillna("").astype(str)
    result = result[
        result["movement_type"].eq("issue")
        | source_names.eq("completion_ack")
    ]
    if "id" in result and reversed_ids:
        result = result[~result["id"].astype(str).isin(reversed_ids)]
    return set(pd.to_datetime(result["movement_date"], errors="coerce").dropna().dt.date)
