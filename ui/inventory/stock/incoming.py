from datetime import timedelta

import streamlit as st

from automation.production_reference import load_production_reference
from db.inventory.container.repository import load_inventory_containers
from db.inventory.core.queries import load_recent_inventory_outbound
from db.inventory.planning.incoming import (
    LOOKBACK_DAYS,
    build_incoming_executive_view,
    build_inventory_audit_issues,
    build_incoming_inventory_forecast,
    normalize_forecast_usage,
)
from db.inventory.planning.uv_consumption import (
    build_uv_forecast_usage,
    load_uv_consumption_history,
)
from ui.inventory.i18n import t


def render_incoming_inventory_forecast(
    supabase, department, category, inventory_df, today,
    forecast_usage_df=None,
):
    st.subheader(t("库存与最近到货联动"))
    if department == "UV":
        st.caption(t(
            "UV 货柜联动使用消耗模型中的 Google Sheets 日耗，并自动扣减库存，不做仓库申报对比。"
        ))
    else:
        st.caption(t(
            "货柜联动沿用上方点货预测的综合日耗；仓库手工出库只用于核对录入差异。"
        ))
    if inventory_df.empty:
        st.info(t("暂无库存数据"))
        return
    try:
        if department == "UV":
            uv_model = load_uv_consumption_history(supabase, today)
            if category:
                uv_model = uv_model[uv_model["品类"] == category]
            system_usage = build_uv_forecast_usage(uv_model)
            if system_usage.empty:
                st.info(t("最近 14 天暂无已同步的 UV 每日消耗数据"))
                return
        else:
            system_usage = normalize_forecast_usage(
                forecast_usage_df, department, category
            )
        if system_usage.empty and department != "UV":
            reference = load_production_reference(department, category)
            if not _render_reference_status(reference, today):
                return
            system_usage = reference.data
        containers = load_inventory_containers(
            supabase, department=department, category=category,
            statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
        )
        outbound = (
            load_recent_inventory_outbound(
                supabase, department,
                today - timedelta(days=LOOKBACK_DAYS - 1),
                category,
            )
            if department == "DTF" else None
        )
        forecast = build_incoming_inventory_forecast(
            inventory_df, containers, system_usage, outbound, today,
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
    if (forecast["判断"] == "已到柜待入库").any():
        st.warning(t("有货柜已经到柜但尚未入库，请仓库尽快确认入库。"))
    if (forecast["判断"] == "到货后库存仍偏低").any():
        st.warning(t("部分 SKU 到货后预计仍不足 14 天，请提前安排下一批。"))
    audit_issues = build_inventory_audit_issues(forecast)
    if not audit_issues.empty:
        st.warning(
            t("发现 {count} 个 SKU 的仓库申报与系统生产不一致。").format(
                count=len(audit_issues)
            )
        )
        st.dataframe(
            audit_issues, hide_index=True, width="stretch",
            column_config={
                "系统日均": st.column_config.NumberColumn(format="%.1f"),
                "仓库申报日均": st.column_config.NumberColumn(format="%.1f"),
                "日均差额": st.column_config.NumberColumn(format="%+.1f"),
                "差异比例": st.column_config.NumberColumn(format="%.0f%%"),
                "核对建议": st.column_config.TextColumn(width="large"),
            },
        )
    executive_view = build_incoming_executive_view(forecast)
    st.dataframe(
        executive_view, hide_index=True, width="stretch",
        column_config={
            "SKU": st.column_config.TextColumn(width="large"),
            "判断": st.column_config.TextColumn(width="medium"),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "日耗": st.column_config.NumberColumn(format="%.1f"),
            "可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "到货日": st.column_config.DateColumn(),
            "到货数量": st.column_config.NumberColumn(format="%d"),
            "到货前缺口": st.column_config.NumberColumn(format="%d"),
            "到货后可撑": st.column_config.NumberColumn(format="%.1f 天"),
        },
    )
    with st.expander(t("查看完整计算明细")):
        st.dataframe(
            forecast, hide_index=True, width="stretch",
            column_config={
                "当前库存": st.column_config.NumberColumn(format="%d"),
                "系统日均": st.column_config.NumberColumn(format="%.1f"),
                "仓库申报日均": st.column_config.NumberColumn(format="%.1f"),
                "当前可撑天数": st.column_config.NumberColumn(
                    format="%.1f 天"
                ),
                "预计/实际到货": st.column_config.DateColumn(),
                "距到货天数": st.column_config.NumberColumn(format="%d 天"),
                "到货前预计剩余": st.column_config.NumberColumn(format="%d"),
                "到货前缺口": st.column_config.NumberColumn(format="%d"),
                "货柜数量": st.column_config.NumberColumn(format="%d"),
                "到货后预计库存": st.column_config.NumberColumn(format="%d"),
                "到货后可撑天数": st.column_config.NumberColumn(
                    format="%.1f 天"
                ),
            },
        )


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
