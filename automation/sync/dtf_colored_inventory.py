import pandas as pd

from automation.sync.colored_source import (
    build_colored_platform_audit,
    list_colored_cached_dates,
    load_daily_colored_production,
    load_daily_colored_production_source,
)
from db.inventory.core.queries import load_inventory_items
from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.operations.adjustments import apply_adjustment_rows
from utils.erp.inventory_review import (
    build_colored_tshirt_inventory_review,
    build_colored_tshirt_source_mapping,
)
from automation.sync.colored_models import (
    build_colored_consumption_wide_table,
    build_colored_forecast_usage,
    build_colored_reconciliation_backlog as _build_reconciliation_backlog,
    load_colored_consumption_history,
)
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


CATEGORY = "彩色短袖"
SOURCE_TYPE = "production_sync"
AGGREGATE_PLATFORM = "全部衣服平台"
COLORED_MAPPING_RULE_VERSION = "colored-v2-l-to-green"


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


def build_colored_daily_preview(supabase, current_date):
    daily = load_daily_colored_production(
        current_date, supabase=supabase
    )
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


def build_colored_mapping_audit(current_date, supabase=None):
    detail, metadata = load_daily_colored_production_source(
        current_date, supabase=supabase
    )
    if detail.empty:
        return pd.DataFrame(), metadata
    production = detail.rename(columns={"生产数量": "数量"}).copy()
    production["部门"] = "DTF"
    production["品类"] = CATEGORY
    production["材质"] = "180g"
    return build_colored_tshirt_source_mapping(production), metadata


def build_colored_mapping_wide_table(source_map):
    columns = [
        "生产平台", "原始颜色", "标准颜色", "库存颜色口径",
        "尺码转换", "转换状态", *SIZE_COLUMNS, "其他/异常",
    ]
    if source_map is None or source_map.empty:
        return pd.DataFrame(columns=columns)
    source = source_map.copy()
    source["尺码转换项"] = source.apply(
        lambda row: (
            str(row["原始生产尺码"])
            if str(row["原始生产尺码"]) == str(row["标准尺码"])
            else f"{row['原始生产尺码']} → {row['标准尺码']}"
        ),
        axis=1,
    )
    source["尺码列"] = source["标准尺码"].where(
        source["标准尺码"].isin(SIZE_COLUMNS), "其他/异常"
    )
    index = [
        "生产平台", "原始生产颜色", "标准颜色", "库存颜色口径",
        "转换状态",
    ]
    conversion = (
        source.groupby(index, dropna=False, as_index=False)["尺码转换项"]
        .agg(lambda values: "；".join(dict.fromkeys(values)))
        .rename(columns={"尺码转换项": "尺码转换"})
    )
    wide = source.pivot_table(
        index=index,
        columns="尺码列",
        values="生产数量",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide = wide.merge(conversion, on=index, how="left")
    wide = wide.rename(columns={"原始生产颜色": "原始颜色"})
    for column in [*SIZE_COLUMNS, "其他/异常"]:
        if column not in wide:
            wide[column] = 0
    return wide[columns].sort_values(
        ["转换状态", "生产平台", "标准颜色"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def apply_colored_daily_deduction(
    supabase, preview, movement_date, created_by="system",
):
    rows = preview[preview["状态"] == "可扣减"].copy()
    if rows.empty:
        return 0
    unresolved = int(pd.to_numeric(
        preview.get("未扣数量", 0), errors="coerce"
    ).fillna(0).sum())
    base_reason = (
        colored_partial_reason(movement_date)
        if unresolved else colored_daily_reason(movement_date)
    )
    _source, metadata = load_daily_colored_production_source(
        movement_date, supabase=supabase
    )
    included = "、".join(metadata.get("included_platforms") or ()) or "未知"
    reason = (
        f"{base_reason}｜来源 {included}｜映射规则 "
        f"{COLORED_MAPPING_RULE_VERSION}"
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


def build_colored_reconciliation_backlog(
    supabase, current_date, days=14,
):
    return _build_reconciliation_backlog(
        supabase, current_date, days,
        load_deducted_total=load_colored_day_deducted_total,
        build_preview=build_colored_daily_preview,
    )


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
            "生产平台": item.get("生产平台", ""),
            "原始生产颜色": item.get("原始生产颜色", ""),
            "原始生产尺码": item.get("原始生产尺码", ""),
        })
    result = pd.DataFrame(rows)
    if "未扣数量" not in result:
        result["未扣数量"] = 0
    result["未扣数量"] = result["未扣数量"].fillna(0).astype(int)
    return result
