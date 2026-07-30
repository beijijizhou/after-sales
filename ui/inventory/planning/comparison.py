import pandas as pd
import streamlit as st

from automation.production_period import load_period_production_model
from db.inventory.planning.consumption import (
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.planning.consumption_comparison import (
    build_period_model_comparison,
)
from db.inventory.planning.demand_anomaly import load_daily_outbound_history
from db.inventory.planning.uv_consumption import (
    UV_CONSUMPTION_LOOKBACK_DAYS,
    UV_DAILY_ORDERS_SPREADSHEET_URL,
    build_uv_container_coverage,
    load_uv_consumption_history,
)
from db.inventory.container.repository import load_inventory_containers
from db.inventory.core.constants import SIZE_COLUMNS
from ui.inventory.i18n import t
from ui.inventory.planning.accuracy import (
    render_model_accuracy_summary,
)


def render_model_comparison(
    model_df, outbound_df, current_date, category="黑白短袖"
):
    days = st.selectbox(
        t("统计周期"),
        [3, 7, 14, 28],
        index=2,
        format_func=lambda value: f"{value} {t('天')}",
        key="inventory_consumption_comparison_days",
    )
    production = load_period_production_model(
        current_date, days, category
    )
    comparison_df = build_period_model_comparison(
        model_df, outbound_df, production.data, current_date, days,
        production.effective_days,
    )
    render_model_comparison_result(
        comparison_df,
        production.effective_days,
        production.start_date,
        production.end_date,
        requested_days=days,
    )


def render_model_comparison_result(
    comparison_df, platform_days, start_date, end_date,
    key_prefix="inventory", requested_days=None,
):
    st.subheader(t("三种消耗模型对比"))
    st.caption(t(
        "15,000单是固定基准；仓库模型来自每日出库；平台模型只使用完整平台数据。"
    ))
    if comparison_df.empty:
        st.info(t("暂无周期对比数据"))
        return

    warehouse_intervals = int(comparison_df["仓库统计区间数"].max())
    st.caption(
        f"{t('仓库有效出库区间')}：{warehouse_intervals}｜"
        f"{t('平台有效天数')}：{platform_days}"
        + (
            f"（{start_date} 至 {end_date}）"
            if platform_days else ""
        )
    )
    if requested_days and platform_days < requested_days:
        st.warning(t("平台完整数据天数不足，平台模型仅供阶段性参考。"))
    render_model_accuracy_summary(comparison_df)

    view = st.selectbox(
        t("查看模型"),
        [
            t("三模型总览"),
            t("15,000模型"),
            t("仓库出库模型"),
            t("平台生产模型"),
        ],
        key=f"{key_prefix}_consumption_model_view",
    )
    if view != t("三模型总览"):
        field = {
            t("15,000模型"): "15,000模型日耗",
            t("仓库出库模型"): "仓库出库日均",
            t("平台生产模型"): "平台生产日均",
        }[view]
        _render_model_detail(comparison_df, field, view)
        return

    _render_totals(comparison_df)
    display_df = comparison_df.copy()
    display_df["颜色"] = display_df["颜色"].map(t)
    styled_df = display_df.style.apply(highlight_comparison, axis=1)
    st.dataframe(
        styled_df, hide_index=True, width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t("尺码")),
            "15,000模型日耗": st.column_config.NumberColumn(
                t("15,000模型日耗"), format="%.1f"
            ),
            "仓库出库日均": st.column_config.NumberColumn(
                t("仓库出库日均"), format="%.1f"
            ),
            "平台生产日均": st.column_config.NumberColumn(
                t("平台生产日均"), format="%.1f"
            ),
            "三模型平均日耗": st.column_config.NumberColumn(
                "三模型平均日耗", format="%.1f"
            ),
            "仓库/模型": st.column_config.NumberColumn(
                t("仓库/模型"), format="%.1f%%"
            ),
            "平台/模型": st.column_config.NumberColumn(
                t("平台/模型"), format="%.1f%%"
            ),
            "仓库有效区间数": st.column_config.NumberColumn(format="%d"),
            "仓库统计区间数": st.column_config.NumberColumn(format="%d"),
            "平台有效天数": st.column_config.NumberColumn(format="%d"),
        },
    )
def render_consumption_models(
    supabase, department, category, order_quantity, current_date,
    visible_sizes=None, inventory_df=None,
):
    if department == "UV":
        render_uv_consumption_model(
            supabase, category, current_date, visible_sizes, inventory_df
        )
        return
    if category != "黑白短袖":
        st.info(t("当前品类暂无消耗模型"))
        return
    try:
        model_df = scale_consumption_model(
            load_consumption_model(supabase, category), order_quantity
        )
        outbound_df = load_daily_outbound_history(
            supabase, department, category, current_date
        )
        if visible_sizes:
            model_df = model_df[model_df["size"].isin(visible_sizes)]
            outbound_df = outbound_df[
                outbound_df["尺码"].isin(visible_sizes)
            ]
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    render_model_comparison(
        model_df, outbound_df, current_date, category
    )


def render_uv_consumption_model(
    supabase, category, current_date, visible_sizes=None, inventory_df=None
):
    try:
        model_df = load_uv_consumption_history(supabase, current_date)
        if category:
            model_df = model_df[model_df["品类"] == category]
        if visible_sizes:
            model_df = model_df[model_df["型号"].isin(visible_sizes)]
        containers = load_inventory_containers(
            supabase,
            department="UV",
            category=category or None,
            statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
        )
        coverage_df = build_uv_container_coverage(
            model_df, inventory_df, containers
        )
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    st.subheader("UV 每日消耗与货柜")
    st.caption(
        f"每日消耗按 Google Sheets 最近 {UV_CONSUMPTION_LOOKBACK_DAYS} 天"
        "的有效数据日计算，并按品类、材质、颜色、型号连接当前库存和最近货柜。"
    )
    st.link_button("打开 UV 每日订单表", UV_DAILY_ORDERS_SPREADSHEET_URL)
    if model_df.empty:
        st.info("最近 14 天暂无已同步的 UV 每日消耗数据")
        return
    daily_total = float(model_df["每日消耗"].sum())
    effective_days = int(model_df["有效数据天数"].max())
    daily_col, days_col = st.columns(2)
    daily_col.metric("一天消耗", f"{daily_total:,.1f} 件")
    days_col.metric("计算所用有效天数", f"{effective_days} 天")
    if effective_days < UV_CONSUMPTION_LOOKBACK_DAYS:
        st.warning(
            f"最近 14 天中只有 {effective_days} 天已同步；"
            "当前日均仅按这些有效日期计算。"
        )
    st.dataframe(
        coverage_df,
        hide_index=True,
        width="stretch",
        column_config={
            "每日消耗": st.column_config.NumberColumn(format="%.1f"),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "当前可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "预计到货日期": st.column_config.DateColumn(),
            "货柜数量": st.column_config.NumberColumn(format="%d"),
            "到货后可撑天数": st.column_config.NumberColumn(
                format="%.1f 天"
            ),
        },
    )


def _render_totals(df):
    columns = st.columns(4)
    values = [
        ("15,000模型日耗", "15,000模型"),
        ("仓库出库日均", "仓库出库模型"),
        ("平台生产日均", "平台生产模型"),
        ("三模型平均日耗", "三模型平均"),
    ]
    for column, (field, label) in zip(columns, values):
        value = pd.to_numeric(df[field], errors="coerce").sum(min_count=1)
        column.metric(t(label), f"{value:,.0f}" if pd.notna(value) else "—")


def _render_model_detail(df, field, title):
    values = df[["颜色", "尺码", field]].copy()
    wide = values.pivot(index="颜色", columns="尺码", values=field)
    wide = wide.reindex(index=["黑", "白"], columns=SIZE_COLUMNS)
    wide = wide.reset_index()
    wide["颜色"] = wide["颜色"].map(t)
    total = pd.to_numeric(values[field], errors="coerce").sum(min_count=1)
    st.metric(
        f"{title} {t('日均合计')}",
        f"{total:,.1f}" if pd.notna(total) else "—",
    )
    st.dataframe(
        wide, hide_index=True, width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            **{
                size: st.column_config.NumberColumn(size, format="%.1f")
                for size in SIZE_COLUMNS
            },
        },
    )


def highlight_comparison(row):
    styles = []
    for column in row.index:
        ratio_field = {
            "仓库出库日均": "仓库/模型",
            "仓库/模型": "仓库/模型",
            "平台生产日均": "平台/模型",
            "平台/模型": "平台/模型",
        }.get(column)
        ratio = pd.to_numeric(row.get(ratio_field), errors="coerce")
        if pd.notna(ratio) and abs(float(ratio) - 100) >= 30:
            styles.append(
                "background-color: #ffd6d6; color: #8a0000; font-weight: 700;"
            )
        elif pd.notna(ratio) and abs(float(ratio) - 100) >= 15:
            styles.append(
                "background-color: #fff1cc; color: #7a4a00; font-weight: 700;"
            )
        else:
            styles.append("")
    return styles
