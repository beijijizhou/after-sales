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


def colored_partial_reason(movement_date):
    return f"{colored_daily_reason(movement_date)}｜部分扣减"


def load_colored_day_deducted_total(supabase, movement_date):
    summary = load_colored_day_deducted_by_sku(supabase, movement_date)
    return int(summary["已扣数量"].sum()) if not summary.empty else 0


def load_colored_day_deducted_by_sku(supabase, movement_date):
    rows = (
        supabase.table("inventory_movements")
        .select(
            "color,size,quantity_change,reason,batch_id,reversal_of_batch_id"
        )
        .eq("department", "DTF")
        .eq("category", CATEGORY)
        .eq("movement_date", movement_date.isoformat())
        .execute().data
        or []
    )
    if not rows:
        return pd.DataFrame(columns=["颜色", "尺码", "已扣数量"])
    movements = pd.DataFrame(rows)
    reversed_ids = set(
        movements.get("reversal_of_batch_id", pd.Series(dtype=str))
        .dropna().astype(str)
    )
    active = movements[
        movements["reversal_of_batch_id"].isna()
        & movements["reason"].fillna("").astype(str).str.startswith(
            colored_daily_reason(movement_date)
        )
        & pd.to_numeric(
            movements["quantity_change"], errors="coerce"
        ).fillna(0).lt(0)
    ].copy()
    if reversed_ids:
        active = active[~active["batch_id"].astype(str).isin(reversed_ids)]
    if active.empty:
        return pd.DataFrame(columns=["颜色", "尺码", "已扣数量"])
    active["颜色"] = active["color"].map(normalize_color)
    active["尺码"] = active["size"].fillna("").astype(str).str.strip()
    active["已扣数量"] = pd.to_numeric(
        active["quantity_change"], errors="coerce"
    ).fillna(0).abs().astype(int)
    return active.groupby(
        ["颜色", "尺码"], as_index=False
    )["已扣数量"].sum()


def load_daily_colored_production_source(
    current_date, require_complete=False
):
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
    if require_complete and not metadata.get("is_complete"):
        return pd.DataFrame(), metadata
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


def load_daily_colored_production(current_date, require_complete=False):
    detail, _metadata = load_daily_colored_production_source(
        current_date, require_complete=require_complete
    )
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
    deducted = load_colored_day_deducted_by_sku(supabase, current_date)
    if not deducted.empty:
        daily = daily.merge(deducted, on=["颜色", "尺码"], how="left")
        daily["已扣数量"] = pd.to_numeric(
            daily["已扣数量"], errors="coerce"
        ).fillna(0)
        daily["生产数量"] = (
            daily["生产数量"] - daily["已扣数量"]
        ).clip(lower=0)
        daily = daily[daily["生产数量"] > 0].drop(columns=["已扣数量"])
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
    unresolved = int(pd.to_numeric(
        preview.get("未扣数量", 0), errors="coerce"
    ).fillna(0).sum())
    reason = (
        colored_partial_reason(movement_date)
        if unresolved else colored_daily_reason(movement_date)
    )
    adjustment = pd.DataFrame({
        "日期": [movement_date] * len(rows),
        "操作": ["扣减"] * len(rows),
        "品牌": rows["品牌"].tolist(),
        "材质": rows["材质"].tolist(),
        "颜色": rows["颜色"].tolist(),
        "尺码": rows["尺码"].tolist(),
        "数量": rows["预计扣减"].astype(int).tolist(),
        "成本": [pd.NA] * len(rows),
        "备注": [reason] * len(rows),
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
        daily = load_daily_colored_production(
            target_date, require_complete=False
        )
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


def build_colored_reconciliation_backlog(
    supabase, current_date, days=14,
):
    rows = []
    for offset in range(int(days)):
        movement_date = current_date.fromordinal(
            current_date.toordinal() - offset
        )
        source, metadata = load_daily_colored_production_source(
            movement_date
        )
        if source.empty:
            continue
        deducted = load_colored_day_deducted_total(
            supabase, movement_date
        )
        if deducted <= 0:
            continue
        source_quantity = int(pd.to_numeric(
            source["生产数量"], errors="coerce"
        ).fillna(0).sum())
        remaining = max(source_quantity - deducted, 0)
        missing = tuple(metadata.get("missing_platforms") or ())
        if remaining <= 0 and not missing:
            continue
        preview = build_colored_daily_preview(supabase, movement_date)
        deductable = int(pd.to_numeric(
            preview.get("预计扣减", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0).sum())
        unresolved = max(remaining - deductable, 0)
        if deductable:
            status = "有库存差额可继续扣减"
        elif unresolved:
            status = "等待补库存或修正 SKU"
        else:
            status = "等待补齐平台数据"
        rows.append({
            "日期": movement_date,
            "生产数据": source_quantity,
            "已扣库存": deducted,
            "当前可补扣": deductable,
            "库存/SKU待核对": unresolved,
            "尚未读取平台": "、".join(missing) or "无",
            "状态": status,
        })
    return pd.DataFrame(rows)


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
