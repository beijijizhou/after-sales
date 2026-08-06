import json
import pandas as pd

from automation.production_cache import CACHE_DIR
from automation.production import PLATFORMS_BY_DEPARTMENT
from db.inventory.core.queries import load_inventory_items
from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.operations.adjustments import apply_adjustment_rows
from utils.erp.inventory_review import build_colored_tshirt_inventory_review
from utils.erp.catalog import normalize_color


CATEGORY = "彩色短袖"
SOURCE_TYPE = "production_sync"
AGGREGATE_PLATFORM = "全部衣服平台"


def colored_daily_reason(movement_date):
    return f"彩色短袖生产自动扣减 {movement_date:%Y-%m-%d}"


def load_colored_day_deducted_total(supabase, movement_date):
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", "DTF")
        .eq("category", CATEGORY)
        .eq("movement_date", movement_date.isoformat())
        .eq("reason", colored_daily_reason(movement_date))
        .lt("quantity_change", 0)
        .execute().data
    )
    return sum(abs(int(row.get("quantity_change") or 0)) for row in rows)


def load_daily_colored_production_source(current_date):
    candidates = []
    for path in CACHE_DIR.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            metadata.get("platform") == AGGREGATE_PLATFORM
            and metadata.get("start_date") == current_date.isoformat()
            and metadata.get("end_date") == current_date.isoformat()
            and path.with_suffix(".parquet").exists()
        ):
            candidates.append((str(metadata.get("saved_at") or ""), path))
    if not candidates:
        return pd.DataFrame(), {}
    metadata_path = max(candidates)[1]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw = pd.read_parquet(metadata_path.with_suffix(".parquet"))
    if "生产项状态" in raw:
        raw = raw[~raw["生产项状态"].astype(str).str.contains("取消", na=False)]
    daily = raw[(raw["部门"] == "DTF") & (raw["品类"] == CATEGORY)].copy()
    if daily.empty:
        return pd.DataFrame(), metadata
    daily["数量"] = pd.to_numeric(daily["数量"], errors="coerce").fillna(0)
    daily["颜色"] = daily["颜色"].map(normalize_color)
    if "运营商" not in daily:
        daily["运营商"] = "未标记平台"
    daily["运营商"] = (
        daily["运营商"].fillna("").astype(str).str.strip()
        .replace("", "未标记平台")
    )
    detail = (
        daily.groupby(["运营商", "颜色", "尺码"], as_index=False)
        .agg(生产数量=("数量", "sum"), 生产记录数=("数量", "size"))
    )
    return detail, metadata


def load_daily_colored_production(current_date):
    detail, _metadata = load_daily_colored_production_source(current_date)
    if detail.empty:
        return pd.DataFrame()
    return detail.groupby(
        ["颜色", "尺码"], as_index=False
    )["生产数量"].sum()


def build_colored_platform_audit(current_date):
    detail, metadata = load_daily_colored_production_source(current_date)
    quantities = {}
    counts = {}
    if not detail.empty:
        quantities = detail.groupby("运营商")["生产数量"].sum().to_dict()
        counts = detail.groupby("运营商")["生产记录数"].sum().to_dict()
    included = {
        str(value).strip()
        for value in metadata.get("included_platforms") or []
    }
    missing = {
        str(value).strip()
        for value in metadata.get("missing_platforms") or []
    }
    configured = list(PLATFORMS_BY_DEPARTMENT.get("DTF", ()))
    extras = sorted((set(quantities) | included | missing) - set(configured))
    rows = []
    for platform in [*configured, *extras]:
        if platform in missing:
            status = "读取失败/缺失"
        elif platform in included or platform in quantities:
            status = "已读取"
        else:
            status = "未确认"
        rows.append({
            "平台": platform,
            "读取状态": status,
            "原始生产件数": int(quantities.get(platform, 0)),
            "生产记录数": int(counts.get(platform, 0)),
        })
    return pd.DataFrame(rows), metadata


def build_colored_daily_preview(supabase, current_date):
    daily = load_daily_colored_production(current_date)
    if daily.empty:
        return pd.DataFrame()
    production = daily.rename(columns={
        "颜色": "颜色", "尺码": "尺码", "生产数量": "数量",
    })
    production["部门"] = "DTF"
    production["品类"] = CATEGORY
    production["材质"] = "180g"
    production["运营商"] = "全部衣服平台"
    inventory = load_inventory_items(supabase, "DTF", CATEGORY)
    source, allocation = build_colored_tshirt_inventory_review(
        production, inventory
    )
    return _cap_allocation_at_zero(source, allocation)


def apply_colored_daily_deduction(
    supabase, preview, movement_date, created_by="system",
):
    rows = preview[preview["状态"] == "可扣减"].copy()
    if rows.empty:
        return 0
    adjustment = pd.DataFrame({
        "日期": [movement_date] * len(rows),
        "操作": ["扣减"] * len(rows),
        "品牌": rows["品牌"].tolist(),
        "材质": rows["材质"].tolist(),
        "颜色": rows["颜色"].tolist(),
        "尺码": rows["尺码"].tolist(),
        "数量": rows["预计扣减"].astype(int).tolist(),
        "成本": [pd.NA] * len(rows),
        "备注": [
            colored_daily_reason(movement_date)
        ] * len(rows),
    })
    apply_adjustment_rows(
        supabase, "DTF", CATEGORY, adjustment,
        created_by=created_by, source_type=SOURCE_TYPE,
    )
    return int(rows["预计扣减"].sum())


def load_colored_consumption_history(supabase, current_date, days=14):
    frames = []
    effective_days = 0
    for offset in range(int(days)):
        target_date = current_date.fromordinal(
            current_date.toordinal() - offset
        )
        daily = load_daily_colored_production(target_date)
        if daily.empty:
            continue
        effective_days += 1
        daily = daily.copy()
        daily["颜色"] = daily["颜色"].replace({"浅灰": "灰色"})
        frames.append(daily)
    if not frames:
        return pd.DataFrame(columns=["颜色", "尺码", "每日消耗", "有效天数"])
    frame = pd.concat(frames, ignore_index=True)
    summary = (
        frame.groupby(["颜色", "尺码"], as_index=False)["生产数量"].sum()
    )
    summary["每日消耗"] = summary["生产数量"] / effective_days
    summary["有效天数"] = effective_days
    return summary[["颜色", "尺码", "每日消耗", "有效天数"]]


def build_colored_forecast_usage(history):
    if history is None or history.empty:
        return pd.DataFrame(columns=[
            "department", "category", "planning_material",
            "color", "size", "system_daily_usage",
        ])
    result = history.rename(columns={
        "颜色": "color", "尺码": "size",
        "每日消耗": "system_daily_usage",
    }).copy()
    result["department"] = "DTF"
    result["category"] = CATEGORY
    result["planning_material"] = "全部品牌/材质"
    return result[[
        "department", "category", "planning_material",
        "color", "size", "system_daily_usage",
    ]]


def build_colored_consumption_wide_table(display):
    columns = ["颜色", "指标", *SIZE_COLUMNS]
    if display is None or display.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for color in sorted(display["颜色"].dropna().astype(str).unique()):
        color_rows = display[display["颜色"].astype(str) == color]
        for field in ["每日消耗", "当前库存", "可撑天数"]:
            values = (
                color_rows.groupby("尺码", dropna=False)[field]
                .sum(min_count=1).to_dict()
            )
            row = {"颜色": color, "指标": field}
            for size in SIZE_COLUMNS:
                value = values.get(size)
                row[size] = round(float(value), 1) if pd.notna(value) else None
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _cap_allocation_at_zero(source, allocation):
    unresolved = source[source["映射状态"] != "已匹配"]
    rows = allocation[allocation["状态"] == "可扣减"].to_dict("records")
    shortages = allocation[allocation["状态"] == "库存不足"]
    for shortage in shortages.to_dict("records"):
        rows.append({
            "品牌": "",
            "材质": "",
            "颜色": shortage["颜色"],
            "尺码": shortage["尺码"],
            "当前库存": 0,
            "预计扣减": 0,
            "扣减后库存": 0,
            "未扣数量": int(shortage["预计扣减"]),
            "状态": "库存为 0（待清点）",
        })
    for item in unresolved.to_dict("records"):
        rows.append({
            "品牌": "", "材质": item.get("生产材质", ""),
            "颜色": item.get("生产颜色", ""),
            "尺码": item.get("生产尺码", ""), "当前库存": 0,
            "预计扣减": int(item["生产数量"]), "扣减后库存": 0,
            "未扣数量": int(item["生产数量"]),
            "状态": f"{item['映射状态']}（待核对）",
        })
    result = pd.DataFrame(rows)
    if "未扣数量" not in result:
        result["未扣数量"] = 0
    result["未扣数量"] = result["未扣数量"].fillna(0).astype(int)
    return result
