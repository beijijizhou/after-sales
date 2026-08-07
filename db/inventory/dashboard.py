from datetime import date, timedelta

import pandas as pd

from db.consumables import (
    load_consumable_batches,
    load_consumable_items,
    load_departments,
)
from db.inventory.container.repository import load_inventory_containers
from utils.daily_consumption import (
    COLORED_REASON_PREFIX,
    UV_REASON_PREFIX,
)


DAILY_FLOW_LABELS = {
    "black_white": "黑白短袖",
    "consumables": "DTF 耗材",
    "colored": "彩色短袖",
    "uv": "UV 生产库存",
}
DAILY_COMPLETION_START_DATE = date(2026, 8, 1)


def load_daily_completion_summary(supabase, today, lookback_days=7):
    summary, _completed, _start_date = load_daily_completion_status(
        supabase, today, lookback_days
    )
    return summary


def load_daily_completion_status(
    supabase, today, lookback_days=None,
    start_date=DAILY_COMPLETION_START_DATE,
):
    if lookback_days is not None:
        rolling_start = today - timedelta(days=lookback_days - 1)
        start_date = max(start_date, rolling_start)
    start_date = min(start_date, today)
    movements = _load_daily_inventory_movements(
        supabase, start_date, today
    )
    departments = load_departments(supabase)
    dtf_rows = departments[departments["code"].eq("DTF")]
    department_id = dtf_rows.iloc[0]["id"] if not dtf_rows.empty else None
    consumable_batches = (
        load_consumable_batches(
            supabase, department_id=department_id,
            start_date=start_date, end_date=today, limit=5000,
        )
        if department_id else pd.DataFrame()
    )
    completed = build_daily_completion_dates(
        movements, consumable_batches
    )
    history_end = today - timedelta(days=1)
    return (
        build_daily_completion_table(completed, start_date, history_end),
        completed,
        start_date,
    )


def build_daily_completion_dates(movements, consumable_batches):
    active_movements = _active_inventory_movements(movements)
    reasons = active_movements.get(
        "reason", pd.Series(index=active_movements.index, dtype=str)
    ).fillna("").astype(str)
    quantities = pd.to_numeric(
        active_movements.get("quantity_change", 0), errors="coerce"
    ).fillna(0)
    dates = pd.to_datetime(
        active_movements.get("movement_date"), errors="coerce"
    ).dt.date
    department = active_movements.get(
        "department", pd.Series(index=active_movements.index, dtype=str)
    ).fillna("").astype(str)
    category = active_movements.get(
        "category", pd.Series(index=active_movements.index, dtype=str)
    ).fillna("").astype(str)
    outbound = quantities.lt(0) & dates.notna()

    colored_reason = COLORED_REASON_PREFIX + " " + dates.astype(str)
    colored_complete = set(dates[
        outbound & department.eq("DTF") & category.eq("彩色短袖")
        & reasons.str.split("｜").str[0].eq(colored_reason)
    ])
    completed = {
        "black_white": set(dates[
            outbound & department.eq("DTF") & category.eq("黑白短袖")
            & reasons.isin({
                "仓库每日出货", "每日正常出货", "每日出货",
                "黑白短袖出库",
            })
        ]),
        "colored": colored_complete,
        "uv": set(dates[
            outbound & department.eq("UV")
            & reasons.str.startswith(UV_REASON_PREFIX)
        ]),
        "consumables": _active_consumable_issue_dates(consumable_batches),
    }
    return completed


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
            "出库项目": label,
            "数据方式": "系统读取" if automatic else "人工登记",
            "已完成天数": len(recorded),
            "检查天数": len(expected),
            "待处理天数": len(missing),
            "待处理日期": "、".join(
                value.strftime("%m/%d") for value in missing
            ) or "无",
            "处理方式": (
                "读取来源并扣减" if automatic else "补录实际出库"
            ),
        })
    return pd.DataFrame(rows)


def build_automatic_missing_dates(completed, start_date, end_date):
    expected = {
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    }
    labels = {
        "colored": DAILY_FLOW_LABELS["colored"],
        "uv": DAILY_FLOW_LABELS["uv"],
    }
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
    completed_labels = []
    pending_labels = []
    for code, label in DAILY_FLOW_LABELS.items():
        target = (
            completed_labels
            if today in set(completed.get(code, set()))
            else pending_labels
        )
        target.append(label)
    return {
        "date": today,
        "completed": completed_labels,
        "pending": pending_labels,
    }


def build_today_completion_table(completed, today):
    rows = []
    for code, label in DAILY_FLOW_LABELS.items():
        automatic = code in {"colored", "uv"}
        is_completed = today in set(completed.get(code, set()))
        if is_completed:
            next_step = "无需处理"
        elif automatic:
            next_step = "今日结束后由系统读取"
        else:
            next_step = "今日结束后补录实际出库"
        rows.append({
            "出库项目": label,
            "数据方式": "系统读取" if automatic else "人工登记",
            "今日状态": "已完成" if is_completed else "进行中",
            "计入补录": "否",
            "下一步": next_step,
        })
    return pd.DataFrame(rows)


def build_daily_operation_table(summary, completed, today):
    if summary.empty:
        return pd.DataFrame(columns=[
            "出库项目", "数据方式", "截止昨日", "待补日期",
            "今日状态", "当前操作",
        ])
    result = summary.copy()
    today_status = build_today_completion_table(
        completed, today
    ).set_index("出库项目")
    result["截止昨日"] = result.apply(
        lambda row: f"{int(row['已完成天数'])}/{int(row['检查天数'])} 天",
        axis=1,
    )
    result["今日状态"] = result["出库项目"].map(
        today_status["今日状态"]
    )
    result["当前操作"] = result.apply(
        _daily_operation_label, axis=1
    )
    return result.rename(columns={"待处理日期": "待补日期"})[[
        "出库项目", "数据方式", "截止昨日", "待补日期",
        "今日状态", "当前操作",
    ]]


def _daily_operation_label(row):
    missing = int(row["待处理天数"])
    if missing:
        if row["数据方式"] == "系统读取":
            return f"系统预览并补扣 {missing} 天"
        return f"补录实际出库 {missing} 天"
    return "无需补录"


def load_inventory_overview(supabase, today):
    inventory_rows = (
        supabase.table("inventory_items")
        .select("department,category,quantity")
        .execute().data
        or []
    )
    inventory = pd.DataFrame(inventory_rows)
    quantities = pd.to_numeric(
        inventory.get("quantity", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0)

    consumables = load_consumable_items(supabase, active_only=True)
    current = pd.to_numeric(
        consumables.get("current_quantity", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0)
    minimum = pd.to_numeric(
        consumables.get("minimum_quantity", pd.Series(dtype=float)),
        errors="coerce",
    )
    low_consumables = int(
        (minimum.notna() & current.le(minimum.fillna(0))).sum()
    )

    containers = load_inventory_containers(
        supabase, statuses=["未到货", "延迟", "在途"]
    )
    container_count = (
        int(containers["container_key"].nunique())
        if not containers.empty and "container_key" in containers else 0
    )
    expected = pd.to_datetime(
        containers.get(
            "expected_arrival_date", pd.Series(dtype="datetime64[ns]")
        ),
        errors="coerce",
    ).dt.date
    delayed = int(
        containers.loc[expected.lt(today), "container_key"].nunique()
    ) if container_count else 0
    arriving = int(containers.loc[
        expected.ge(today) & expected.le(today + timedelta(days=7)),
        "container_key",
    ].nunique()) if container_count else 0
    return {
        "production_skus": len(inventory),
        "production_units": int(quantities.sum()),
        "zero_stock_skus": int(quantities.le(0).sum()),
        "consumable_skus": len(consumables),
        "low_consumable_skus": low_consumables,
        "in_transit_containers": container_count,
        "delayed_containers": delayed,
        "arriving_containers": arriving,
    }


def _load_daily_inventory_movements(supabase, start_date, end_date):
    rows = (
        supabase.table("inventory_movements")
        .select(
            "department,category,movement_date,quantity_change,reason,"
            "batch_id,reversal_of_batch_id"
        )
        .gte("movement_date", start_date.isoformat())
        .lte("movement_date", end_date.isoformat())
        .execute().data
        or []
    )
    return pd.DataFrame(rows)


def _active_inventory_movements(movements):
    if movements is None or movements.empty:
        return pd.DataFrame(columns=[
            "department", "category", "movement_date", "quantity_change",
            "reason", "batch_id", "reversal_of_batch_id",
        ])
    result = movements.copy()
    reversed_ids = set(
        result.get("reversal_of_batch_id", pd.Series(dtype=str))
        .dropna().astype(str)
    )
    if "reversal_of_batch_id" in result:
        result = result[result["reversal_of_batch_id"].isna()]
    if "batch_id" in result and reversed_ids:
        result = result[~result["batch_id"].astype(str).isin(reversed_ids)]
    return result


def _active_consumable_issue_dates(batches):
    if batches is None or batches.empty:
        return set()
    result = batches.copy()
    reversed_ids = set(
        result.get("reversal_of_batch_id", pd.Series(dtype=str))
        .dropna().astype(str)
    )
    result = result[result["movement_type"].eq("issue")]
    if "id" in result and reversed_ids:
        result = result[~result["id"].astype(str).isin(reversed_ids)]
    return set(pd.to_datetime(
        result["movement_date"], errors="coerce"
    ).dropna().dt.date)
