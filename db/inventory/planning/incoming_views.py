"""Human-facing incoming forecast, executive summary and audit tables."""

import pandas as pd

from db.inventory.core.constants import UV_MATERIAL_ORDER, UV_MODEL_ORDER
from utils.sku_sorting import sort_sku_rows


def build_inventory_audit_issues(forecast):
    columns = [
        "品类", "材质口径", "颜色", "规格", "问题", "系统日均",
        "仓库申报日均", "日均差额", "差异比例", "核对建议",
    ]
    if forecast is None or forecast.empty:
        return pd.DataFrame(columns=columns)
    issues = forecast[
        ~forecast["录入核对"].isin(["接近", "无数据", "不适用"])
    ].copy()
    if issues.empty:
        return pd.DataFrame(columns=columns)
    issues["问题"] = issues["录入核对"]
    issues["日均差额"] = (issues["仓库申报日均"] - issues["系统日均"]).round(1)
    issues["差异比例"] = issues.apply(
        lambda row: abs(row["日均差额"]) / row["系统日均"] * 100
        if row["系统日均"] > 0 else None, axis=1,
    )
    issues["核对建议"] = issues.apply(audit_suggestion, axis=1)
    return issues[columns].sort_values(
        ["问题", "差异比例"], ascending=[True, False], na_position="last",
    ).reset_index(drop=True)


def build_incoming_executive_view(forecast):
    columns = [
        "SKU", "判断", "当前库存", "日耗", "可撑天数", "到货计划",
        "在途总量", "到货前缺口", "货柜衔接", "到货后可撑",
    ]
    if forecast is None or forecast.empty:
        return pd.DataFrame(columns=columns)
    result = visible_and_sorted_forecast(forecast)
    pending_containers = result.get(
        "待确认在途货柜", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    pending_schedule = result.get(
        "待确认到货安排", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    pending_overview = result.get(
        "待确认到货概览", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    has_pending = pending_containers.str.strip().ne("")
    exact_containers = result["全部在途货柜"].fillna("").astype(str)
    exact_schedule = result["到货安排"].fillna("").astype(str)
    result.loc[has_pending, "全部在途货柜"] = (
        exact_containers[has_pending].map(
            lambda value: f"{value}；" if value.strip() else ""
        ) + "共享待分配：" + pending_containers[has_pending]
    )
    result.loc[has_pending, "到货安排"] = (
        exact_schedule[has_pending].map(
            lambda value: f"{value}｜" if value.strip() else ""
        ) + pending_schedule[has_pending]
    )
    result["到货计划"] = result.get(
        "到货概览", pd.Series("", index=result.index)
    ).fillna("").astype(str)
    result.loc[has_pending, "到货计划"] = (
        result.loc[has_pending, "到货计划"].map(
            lambda value: f"{value}｜" if value.strip() else ""
        ) + pending_overview[has_pending]
    )
    no_allocated = pd.to_numeric(
        result["在途总量"], errors="coerce"
    ).fillna(0).eq(0)
    result.loc[has_pending & no_allocated, "在途总量"] = pd.NA
    result["货柜衔接"] = result.apply(container_connection_status, axis=1)
    result["SKU"] = result.apply(
        lambda row: "｜".join(value for value in [
            display_text(row.get("材质口径")) or display_text(row.get("品类")),
            display_text(row.get("颜色")), display_text(row.get("规格")),
        ] if value), axis=1,
    )
    result = result.rename(columns={
        "系统日均": "日耗", "当前可撑天数": "可撑天数",
        "到货后可撑天数": "到货后可撑",
    })
    return result[columns].sort_values(
        "可撑天数", ascending=True, kind="stable", na_position="last",
    ).reset_index(drop=True)


def format_forecast(result):
    result = result.rename(columns={
        "department": "部门", "category": "品类",
        "planning_material": "材质口径", "color": "颜色", "size": "规格",
        "current_quantity": "当前库存", "system_daily_usage": "系统日均",
        "manual_daily_usage": "仓库申报日均", "coverage_days": "当前可撑天数",
        "container_no": "全部在途货柜", "arrival_schedule": "到货安排",
        "arrival_overview": "到货概览", "has_overdue_estimate": "包含延期估算",
        "first_arrival_date": "最早到货", "last_arrival_date": "最晚到货",
        "days_to_arrival": "距到货天数", "incoming_quantity": "在途总量",
        "quantity_before_arrival": "到货前预计剩余", "shortage": "到货前缺口",
        "quantity_after_arrival": "到货后预计库存",
        "coverage_after_arrival": "到货后可撑天数",
        "normalized_status": "货柜状态",
    })
    columns = [
        "部门", "品类", "材质口径", "颜色", "规格", "判断", "当前库存",
        "系统日均", "当前可撑天数", "全部在途货柜", "货柜状态", "到货概览",
        "到货安排", "包含延期估算", "最早到货", "最晚到货", "距到货天数",
        "到货前预计剩余", "到货前缺口", "在途总量", "到货后预计库存",
        "到货后可撑天数", "仓库申报日均", "录入核对",
    ]
    return visible_and_sorted_forecast(result[columns])


def visible_and_sorted_forecast(forecast):
    result = forecast.copy()
    if "品类" in result:
        result = result[result["品类"].fillna("").astype(str).str.strip().ne("手机壳")]
    return sort_sku_rows(
        result, material="材质口径", color="颜色", size="规格",
        leading=["部门", "品类"], material_order=UV_MATERIAL_ORDER,
        size_order=UV_MODEL_ORDER,
    )


def container_connection_status(row):
    pending = display_text(row.get("待确认到货概览"))
    allocated = pd.to_numeric(row.get("在途总量"), errors="coerce")
    if pending and (pd.isna(allocated) or allocated <= 0):
        return "分配待确认，暂不能判断"
    if not display_text(row.get("到货概览")):
        return "无明确到货"
    overdue = bool(row.get("包含延期估算", False))
    shortage = pd.to_numeric(row.get("到货前缺口"), errors="coerce")
    if pd.notna(shortage) and shortage > 0:
        return f"{'按明日估算，' if overdue else ''}无法衔接，缺口 {int(shortage):,}片"
    return "按明日估算，可以衔接" if overdue else "可以衔接"


def audit_suggestion(row):
    if row["录入核对"] == "未录入出库":
        return "系统有生产但仓库无匹配出库；检查漏录或颜色/规格映射"
    if row["录入核对"] == "可能录错规格":
        return "仓库有出库但系统无相同 SKU；检查材质、颜色和规格"
    direction = "高于" if row["日均差额"] > 0 else "低于"
    return f"仓库申报{direction}系统生产 {abs(row['日均差额']):.1f}/天"


def display_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in {"", "未填写"} else text
