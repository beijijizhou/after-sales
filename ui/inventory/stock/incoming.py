from datetime import timedelta

import pandas as pd
import streamlit as st

from automation.production_reference import load_production_reference
from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.unallocated import (
    attach_unallocated_cup_cargo,
    build_unallocated_cup_cargo,
)
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
from ui.inventory.display_scope import apply_routine_display_scope
from ui.planning import render_planning_summary


def render_incoming_inventory_forecast(
    supabase, department, category, inventory_df, today,
    forecast_usage_df=None, target_days=55,
):
    department_label = str(department or "").strip()
    st.subheader(f"{department_label} 部门库存与最近到货联动")
    if department == "UV":
        st.caption(t(
            "UV 货柜联动使用消耗模型中的 Google Sheets 日耗，并自动扣减库存，不做仓库申报对比。"
        ))
    elif department == "DTF" and category == "彩色短袖":
        st.caption(
            "彩色短袖使用最近30天平台生产消耗模型并自动扣减库存，"
            "不做仓库申报对比；上方手动调整后的预测日耗、缺口和"
            "建议点货量会同步传递到货柜联动。"
        )
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
        elif department == "DTF" and category == "彩色短袖":
            system_usage = normalize_forecast_usage(
                forecast_usage_df, department, category
            )
            if system_usage.empty:
                st.info("请先在上方生成彩色短袖点货预测")
                return
        else:
            system_usage = normalize_forecast_usage(
                forecast_usage_df, department, category
            )
        if (
            system_usage.empty
            and department != "UV"
            and category != "彩色短袖"
        ):
            reference = load_production_reference(department, category)
            if not _render_reference_status(reference, today):
                return
            system_usage = reference.data
        containers = load_inventory_containers(
            supabase, department=department, category=category,
            statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
        )
        pending_cups = pd.DataFrame()
        if department == "UV" and category in ("", "保温杯"):
            all_uv_containers = load_inventory_containers(
                supabase,
                department="UV",
                statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
            )
            pending_cups = build_unallocated_cup_cargo(all_uv_containers)
        outbound = (
            load_recent_inventory_outbound(
                supabase, department,
                today - timedelta(days=LOOKBACK_DAYS - 1),
                category,
            )
            if department == "DTF" and category != "彩色短袖" else None
        )
        forecast = build_incoming_inventory_forecast(
            inventory_df, containers, system_usage, outbound, today,
            department, target_days=target_days,
        )
        forecast = attach_unallocated_cup_cargo(forecast, pending_cups)
    except Exception as error:
        st.error(f"{t('到货联动加载失败')}：{error}")
        return

    if forecast.empty:
        st.info(t("当前筛选范围暂无库存或消耗数据"))
        return
    if not forecast.empty and (forecast["判断"] == "到货前可能断货").any():
        st.error(t("有 SKU 可能无法支撑到下一柜到货，请提前安排。"))
    if not forecast.empty and (forecast["判断"] == "已到柜待入库").any():
        st.warning(t("有货柜已经到柜但尚未入库，请仓库尽快确认入库。"))
    if not forecast.empty and (forecast["判断"] == "延期柜按明日估算").any():
        st.warning(t("延期货柜已临时按明日到货计算，请及时更新实际预计日期。"))
    if not forecast.empty and (forecast["判断"] == "到货后库存仍偏低").any():
        st.warning(t("部分 SKU 到货后预计仍不足 14 天，请提前安排下一批。"))
    render_planning_summary(
        forecast,
        reorder_column="建议点货量",
        coverage_column="当前可撑天数",
        quantity_unit="件",
        after_incoming_column="扣除在途后建议点货量",
    )
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
    executive_view = build_incoming_executive_view(
        forecast, hide_color=department == "UV"
    )
    st.dataframe(
        executive_view,
        hide_index=True, width="stretch",
        column_config={
            "SKU": st.column_config.TextColumn(),
            "判断": st.column_config.TextColumn(),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "日耗": st.column_config.NumberColumn(format="%.1f"),
            "可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "建议点货": st.column_config.NumberColumn(format="%d"),
            "扣除在途后建议点货": st.column_config.NumberColumn(format="%d"),
            "到货计划": st.column_config.TextColumn(),
            "在途总量": st.column_config.NumberColumn(format="%d"),
            "到货前缺口": st.column_config.NumberColumn(format="%d"),
            "货柜衔接": st.column_config.TextColumn(),
            "到货后可撑": st.column_config.NumberColumn(format="%.1f 天"),
        },
    )
    with st.expander(t("查看完整计算明细")):
        full_detail = apply_routine_display_scope(forecast, department)
        st.dataframe(
            full_detail, hide_index=True, width="stretch",
            column_config={
                "当前库存": st.column_config.NumberColumn(format="%d"),
                "系统日均": st.column_config.NumberColumn(format="%.1f"),
                "仓库申报日均": st.column_config.NumberColumn(format="%.1f"),
                "当前可撑天数": st.column_config.NumberColumn(
                    format="%.1f 天"
                ),
                "目标备货天数": st.column_config.NumberColumn(format="%d 天"),
                "目标库存": st.column_config.NumberColumn(format="%d"),
                "建议点货量": st.column_config.NumberColumn(format="%d"),
                "扣除在途后建议点货量": st.column_config.NumberColumn(format="%d"),
                "最早到货": st.column_config.DateColumn(),
                "最晚到货": st.column_config.DateColumn(),
                "距到货天数": st.column_config.NumberColumn(format="%d 天"),
                "到货前预计剩余": st.column_config.NumberColumn(format="%d"),
                "到货前缺口": st.column_config.NumberColumn(format="%d"),
                "在途总量": st.column_config.NumberColumn(format="%d"),
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
        coverage = reference.coverage_ratio * 100
        scale = (
            1 / reference.coverage_ratio
            if reference.coverage_ratio > 0 else 1
        )
        st.warning(
            f"{t('生产数据不完整，已按可用平台重新分配占比')}："
            + "、".join(reference.missing_platforms)
        )
        st.caption(
            f"可用平台历史占比约 {coverage:.1f}%｜"
            f"估算系数 {scale:.2f}｜{reference.estimate_method}。"
            "当前继续计算库存与到货预测，并标记为估算结果。"
        )
    st.caption(
        f"{t('系统生产数据区间')}：{reference.start_date} 至 "
        f"{reference.end_date}｜{reference.sources} {t('个数据源')}｜"
        f"{t('本地更新时间')}：{reference.saved_at}"
    )
    if reference.end_date and (today - reference.end_date).days > 1:
        st.warning(t("系统生产数据不是最新日期，请先同步生产数据。"))
    return True
