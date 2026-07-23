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
from db.inventory.core.constants import SIZE_COLUMNS
from ui.inventory.i18n import t


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
    st.subheader(t("三种消耗模型对比"))
    st.caption(t(
        "15,000单是固定基准；仓库模型来自每日出库；平台模型只使用完整平台数据。"
    ))
    if comparison_df.empty:
        st.info(t("暂无周期对比数据"))
        return

    warehouse_days = int(comparison_df["仓库有效天数"].max())
    st.caption(
        f"{t('仓库有效天数')}：{warehouse_days}｜"
        f"{t('平台有效天数')}：{production.effective_days}"
        + (
            f"（{production.start_date} 至 {production.end_date}）"
            if production.effective_days else ""
        )
    )
    if production.effective_days < days:
        st.warning(t("平台完整数据天数不足，平台模型仅供阶段性参考。"))

    view = st.selectbox(
        t("查看模型"),
        [
            t("三模型总览"),
            t("15,000模型"),
            t("仓库出库模型"),
            t("平台生产模型"),
        ],
        key="inventory_consumption_model_view",
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
            "仓库/模型": st.column_config.NumberColumn(
                t("仓库/模型"), format="%.1f%%"
            ),
            "平台/模型": st.column_config.NumberColumn(
                t("平台/模型"), format="%.1f%%"
            ),
            "仓库有效天数": st.column_config.NumberColumn(format="%d"),
            "平台有效天数": st.column_config.NumberColumn(format="%d"),
        },
    )


def render_consumption_models(
    supabase, department, category, order_quantity, current_date,
    visible_sizes=None,
):
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


def _render_totals(df):
    columns = st.columns(3)
    values = [
        ("15,000模型日耗", "15,000模型"),
        ("仓库出库日均", "仓库出库模型"),
        ("平台生产日均", "平台生产模型"),
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
