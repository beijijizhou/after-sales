from datetime import timedelta
import math

import pandas as pd
import streamlit as st

from automation.production_reference import load_production_reference
from db.inventory.container.repository import load_inventory_containers
from db.inventory.core.queries import load_recent_inventory_outbound
from ui.inventory.i18n import t
from utils.erp.inventory_mapping import (
    KEY_COLUMNS,
    normalize_inventory_for_planning,
)


LOOKBACK_DAYS = 14


def render_incoming_inventory_forecast(
    supabase, department, category, inventory_df, today
):
    st.subheader(t("库存与最近到货联动"))
    st.caption(t(
        "缺货预测以平台生产数据为准；仓库手工出库只用于核对录入差异。"
    ))
    if inventory_df.empty:
        st.info(t("暂无库存数据"))
        return
    try:
        reference = load_production_reference(department, category)
        if not _render_reference_status(reference, today):
            return
        containers = load_inventory_containers(
            supabase, department=department, category=category,
            statuses=["未到货", "延迟"],
        )
        outbound = load_recent_inventory_outbound(
            supabase, department, today - timedelta(days=LOOKBACK_DAYS - 1),
            category,
        )
        forecast = build_incoming_inventory_forecast(
            inventory_df, containers, reference.data, outbound, today,
            department,
        )
    except Exception as error:
        st.error(f"{t('到货联动加载失败')}：{error}")
        return

    if forecast.empty:
        st.info(t("当前筛选范围没有可匹配的在途库存"))
        return
    if (forecast["判断"] == "到货前可能断货").any():
        st.error(t("有 SKU 可能无法支撑到下一柜到货，请提前安排。"))
    if (forecast["录入核对"] != "接近").any():
        st.warning(t("仓库申报与系统生产存在差异，请核对颜色、规格和品牌。"))
    st.dataframe(
        forecast, hide_index=True, width="stretch",
        column_config={
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "系统日均": st.column_config.NumberColumn(format="%.1f"),
            "仓库申报日均": st.column_config.NumberColumn(format="%.1f"),
            "预计可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "预计到货": st.column_config.DateColumn(),
            "距到货天数": st.column_config.NumberColumn(format="%d 天"),
            "在途数量": st.column_config.NumberColumn(format="%d"),
            "预计缺口": st.column_config.NumberColumn(format="%d"),
        },
    )


def build_incoming_inventory_forecast(
    inventory_df, container_df, system_usage_df, outbound_df, today,
    department,
):
    if container_df.empty:
        return pd.DataFrame()
    current = normalize_inventory_for_planning(inventory_df, department)
    incoming = normalize_inventory_for_planning(container_df, department)
    current = _sum_quantity(current, "quantity", "current_quantity")
    nearest = _nearest_incoming(incoming)
    system = _normalize_usage(system_usage_df, "system_daily_usage")
    manual = _manual_average(outbound_df, department)

    result = nearest.merge(current, on=KEY_COLUMNS, how="left")
    result = result.merge(system, on=KEY_COLUMNS, how="left")
    result = result.merge(manual, on=KEY_COLUMNS, how="left")
    for column in ["current_quantity", "system_daily_usage", "manual_daily_usage"]:
        result[column] = result[column].fillna(0)
    result["days_to_arrival"] = result["expected_arrival_date"].map(
        lambda value: (value - today).days
    )
    result["coverage_days"] = result.apply(_coverage_days, axis=1)
    result["shortage"] = result.apply(_projected_shortage, axis=1)
    result["判断"] = result.apply(_forecast_status, axis=1)
    result["录入核对"] = result.apply(_audit_status, axis=1)
    result = result.rename(columns={
        "category": "品类", "planning_material": "材质口径",
        "color": "颜色", "size": "规格", "current_quantity": "当前库存",
        "system_daily_usage": "系统日均",
        "manual_daily_usage": "仓库申报日均",
        "coverage_days": "预计可撑天数", "container_no": "最近货柜",
        "expected_arrival_date": "预计到货",
        "days_to_arrival": "距到货天数",
        "incoming_quantity": "在途数量", "shortage": "预计缺口",
    })
    columns = [
        "品类", "材质口径", "颜色", "规格", "当前库存", "系统日均",
        "仓库申报日均", "录入核对", "预计可撑天数", "最近货柜",
        "预计到货", "距到货天数", "在途数量", "预计缺口", "判断",
    ]
    return result[columns].sort_values(
        ["预计缺口", "距到货天数"], ascending=[False, True]
    ).reset_index(drop=True)


def _render_reference_status(reference, today):
    if reference.data.empty:
        st.error(t("暂无系统生产数据，当前不计算消耗与缺货。"))
        if reference.missing_platforms:
            st.caption(
                f"{t('缺少生产平台')}："
                + "、".join(reference.missing_platforms)
            )
        return False
    if not reference.is_complete:
        st.error(
            f"{t('生产数据不完整，已停止库存预测')}："
            + "、".join(reference.missing_platforms)
        )
        return False
    st.caption(
        f"{t('系统生产数据区间')}：{reference.start_date} 至 "
        f"{reference.end_date}｜{reference.sources} {t('个数据源')}｜"
        f"{t('本地更新时间')}：{reference.saved_at}"
    )
    if reference.end_date and (today - reference.end_date).days > 1:
        st.warning(t("系统生产数据不是最新日期，请先同步生产数据。"))
    return True


def _sum_quantity(df, source, target):
    result = df.copy()
    result[source] = pd.to_numeric(result.get(source, 0), errors="coerce").fillna(0)
    return result.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        **{target: (source, "sum")}
    )


def _nearest_incoming(df):
    result = df.copy()
    result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce").fillna(0)
    result["expected_arrival_date"] = pd.to_datetime(
        result["expected_arrival_date"], errors="coerce"
    ).dt.date
    result = result.dropna(subset=["expected_arrival_date"])
    result["container_no"] = result["container_no"].fillna(
        result["container_key"]
    ).astype(str)
    nearest_date = result.groupby(KEY_COLUMNS, dropna=False)[
        "expected_arrival_date"
    ].transform("min")
    result = result[result["expected_arrival_date"] == nearest_date]
    return result.groupby(
        [*KEY_COLUMNS, "expected_arrival_date"], dropna=False, as_index=False
    ).agg(
        incoming_quantity=("quantity", "sum"),
        container_no=("container_no", lambda x: " / ".join(sorted(set(x)))),
    )


def _normalize_usage(df, column):
    if df.empty:
        return pd.DataFrame(columns=[*KEY_COLUMNS, column])
    return df.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        **{column: (column, "sum")}
    )


def _manual_average(df, department):
    if df.empty:
        return pd.DataFrame(columns=[*KEY_COLUMNS, "manual_daily_usage"])
    result = normalize_inventory_for_planning(df, department)
    result["manual"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0).abs()
    return result.groupby(KEY_COLUMNS, dropna=False, as_index=False).agg(
        manual_daily_usage=("manual", lambda values: values.sum() / LOOKBACK_DAYS)
    )


def _coverage_days(row):
    return (
        row["current_quantity"] / row["system_daily_usage"]
        if row["system_daily_usage"] > 0 else None
    )


def _projected_shortage(row):
    if row["days_to_arrival"] < 0 or row["system_daily_usage"] <= 0:
        return 0
    return max(math.ceil(
        row["system_daily_usage"] * row["days_to_arrival"]
        - row["current_quantity"]
    ), 0)


def _forecast_status(row):
    if row["days_to_arrival"] < 0:
        return "货柜已延迟"
    if row["system_daily_usage"] <= 0:
        return "暂无系统消耗依据"
    return "到货前可能断货" if row["shortage"] > 0 else "可撑到到货"


def _audit_status(row):
    system, manual = row["system_daily_usage"], row["manual_daily_usage"]
    if system > 0 and manual == 0:
        return "未录入出库"
    if system == 0 and manual > 0:
        return "可能录错规格"
    if system == 0:
        return "无数据"
    return "需核对" if abs(manual - system) / system > 0.3 else "接近"
