import pandas as pd
import streamlit as st

from db.inventory.planning.consumption_comparison import (
    FORECAST_SOURCE_WEIGHTS,
    normalize_forecast_weights,
    scale_forecast_daily_total,
)
from db.inventory.planning.consumption import (
    build_consumption_order_mix_comparison,
    build_consumption_order_mix_table,
)
from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.planning.warehouse_usage import build_warehouse_daily_totals
from ui.inventory.i18n import t
from ui.table_layout import fit_table_height
from utils.runtime import is_deployed_runtime


def render_forecast_model_controls(order_quantity=15000):
    st.subheader(t("点货预测参数"))
    st.info(
        "黑白短袖固定以仓库每日实际出库为消耗基准。"
        "旧订单模型和平台生产数据均不参与点货计算。"
    )
    return normalize_forecast_weights(FORECAST_SOURCE_WEIGHTS)


def render_order_model_breakdown(
    model_df, order_quantity=15000, base_model_df=None,
):
    st.subheader("仓库消耗基准：黑白与尺码结构")
    st.caption(
        "调整前基准来自仓库每日实际出库；自定义总日耗会按该结构等比例缩放，"
        "逐尺码微调除外。"
    )
    base_source = base_model_df if base_model_df is not None else model_df
    breakdown = build_consumption_order_mix_table(model_df)
    if breakdown.empty:
        st.info("暂无仓库出库消耗明细")
        return

    total = int(pd.to_numeric(breakdown["合计"], errors="coerce").sum())
    base_total = pd.to_numeric(
        build_consumption_order_mix_table(base_source).get("合计"),
        errors="coerce",
    ).fillna(0).sum()
    scale_ratio = total / base_total if base_total else 0
    metrics = st.columns(4)
    metrics[0].metric("调整前日耗", f"{base_total:,.1f} 件")
    metrics[1].metric("当前采用日耗", f"{total:,} 件")
    ratio_by_color = breakdown.set_index("颜色")["黑白占比"].to_dict()
    metrics[2].metric(
        "黑 / 白比例",
        f"{float(ratio_by_color.get('黑', 0)):.1f}% / "
        f"{float(ratio_by_color.get('白', 0)):.1f}%",
    )
    metrics[3].metric("整体调整比例", f"{scale_ratio * 100:.1f}%")
    comparison = build_consumption_order_mix_comparison(
        base_source, model_df, "调整前基准",
    )
    st.caption(
        "每格按“调整前→调整后”显示；统一调整比例在上方展示，"
        "占比列只显示调整后的当前占比。"
    )
    st.dataframe(
        comparison,
        hide_index=True,
        width="stretch",
        height=fit_table_height(comparison),
        column_config={
            "颜色": st.column_config.TextColumn("颜色", width="small"),
            **{
                size: st.column_config.TextColumn(size, width="small")
                for size in SIZE_COLUMNS
            },
            "合计": st.column_config.TextColumn("合计", width="small"),
            "黑白占比": st.column_config.TextColumn("当前占比", width="small"),
        },
    )


def render_forecast_calculation(
    comparison_df,
    forecast_model_df,
    platform_days,
    platform_start,
    platform_end,
):
    with st.expander(t("查看预测计算明细")):
        show_platform_diagnostics = not is_deployed_runtime()
        if show_platform_diagnostics:
            if platform_days:
                st.caption(
                    f"{t('平台生产数据')}：{platform_start} 至 "
                    f"{platform_end}｜{platform_days} {t('天')}"
                )
            else:
                st.warning(t("暂无完整平台生产数据，平台数据仅作为核对参考。"))
        detail = comparison_df.merge(
            forecast_model_df.rename(columns={
                "color": "颜色",
                "size": "尺码",
                "consumption_quantity": "最终预测日耗",
            }),
            on=["颜色", "尺码"],
            how="left",
        )
        columns = [
            "颜色", "尺码",
            *(["15,000模型日耗"] if show_platform_diagnostics else []),
            "仓库出库日均",
            *(["平台生产日均"] if show_platform_diagnostics else []),
            "最终预测日耗",
        ]
        st.dataframe(
            detail[[column for column in columns if column in detail]],
            hide_index=True,
            width="stretch",
            column_config={
                column: st.column_config.NumberColumn(
                    t(column), format="%.1f"
                )
                for column in columns[2:]
            },
        )


def render_forecast_usage_adjustment(
    model_df, period_total, period_days, category, period_model_df=None,
    warehouse_outbound_df=None, current_date=None, period_effective_days=None,
):
    source = pd.DataFrame(model_df).copy()
    base_daily = pd.to_numeric(
        source.get("consumption_quantity"), errors="coerce"
    ).fillna(0).sum()
    source_fingerprint = _stable_usage_fingerprint(source)
    with st.container(border=True):
        st.subheader("自定义消耗模型")
        st.markdown(
            """
            <style>
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.forecast-input-highlight) {
                border: 2px solid #f59e0b;
                background: linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%);
                box-shadow: 0 4px 14px rgba(245, 158, 11, 0.16);
            }
            input[aria-label="自定义预测日耗（件）"] {
                min-height: 3.5rem;
                color: #78350f !important;
                -webkit-text-fill-color: #78350f !important;
                background: #fffbeb !important;
                font-size: 1.75rem !important;
                font-weight: 900 !important;
                text-align: center;
            }
            </style>
            <div class="forecast-input-highlight"></div>
            <div style="
                display: inline-block;
                margin: 0.15rem 0 0.55rem 0;
                padding: 0.42rem 0.85rem;
                border-left: 6px solid #b45309;
                border-radius: 0.35rem;
                color: #78350f;
                background: #fef3c7;
                font-size: 1.45rem;
                font-weight: 900;
                line-height: 1.25;
            ">自定义预测日耗（件）</div>
            """,
            unsafe_allow_html=True,
        )
        custom_key = (
            f"forecast_custom_daily_total_{category}_{period_days}_"
            f"{source_fingerprint}"
        )
        custom_daily = st.number_input(
            "自定义预测日耗（件）",
            label_visibility="collapsed",
            min_value=0,
            max_value=1000000,
            value=max(int(round(base_daily)), 0),
            step=max(int(round(base_daily * 0.05)), 1),
            key=custom_key,
            help="默认等于消耗模型日耗；修改后点货量、缺口和货柜联动会同步重算。",
        )
        st.markdown(
            """
            <div style="
                margin: 0.35rem 0 0.8rem 0;
                color: #78350f;
                font-size: 1.05rem;
                font-weight: 800;
            ">修改这里后，下面所有点货数据立即按新日耗重新计算。</div>
            """,
            unsafe_allow_html=True,
        )
        warehouse_daily = build_warehouse_daily_totals(
            warehouse_outbound_df, current_date, period_days,
        ) if current_date is not None else pd.DataFrame()
        warehouse_total = pd.to_numeric(
            warehouse_daily.get("仓库出库量"), errors="coerce"
        ).fillna(0).sum() if not warehouse_daily.empty else 0
        recorded_days = int(warehouse_daily["日期"].nunique()) if not warehouse_daily.empty else 0
        warehouse_daily_average = (
            warehouse_total / recorded_days if recorded_days else 0
        )
        show_platform_diagnostics = (
            category != "黑白短袖" or not is_deployed_runtime()
        )
        metric_count = (
            3 if category == "黑白短袖" and show_platform_diagnostics
            else 2 if category == "黑白短袖"
            else 2
        )
        metrics = st.columns(metric_count)
        metrics[0].metric("原基础综合日耗", f"{base_daily:,.1f} 件")
        effective_days = max(int(period_effective_days or 0), 0)
        platform_daily_average = (
            float(period_total) / effective_days if effective_days else 0
        )
        if category == "黑白短袖":
            warehouse_metric_index = 2 if show_platform_diagnostics else 1
            if show_platform_diagnostics:
                metrics[1].metric(
                    "平台日均生产",
                    f"{platform_daily_average:,.1f} 件/天",
                )
            metrics[warehouse_metric_index].metric(
                "仓库日均出库",
                f"{warehouse_daily_average:,.1f} 件/天",
            )
            st.caption(
                f"仓库统计覆盖 {recorded_days}/{int(period_days)} 个完整自然日；"
                "日平均只按有登记的日期计算，缺失日期不当作零。"
            )
        else:
            metrics[1].metric(
                "平台日均生产",
                f"{platform_daily_average:,.1f} 件/天",
            )
        if show_platform_diagnostics:
            st.caption(
                f"平台累计读取 {period_total:,.0f} 件｜"
                f"实际覆盖 {effective_days}/{int(period_days)} 个完整自然日；"
                "平台日均按实际有数据日期计算。"
            )
    adjusted = scale_forecast_daily_total(source, custom_daily)
    customized = int(custom_daily) != max(int(round(base_daily)), 0)
    period_source = pd.DataFrame(period_model_df).rename(columns={
        "颜色": "color", "尺码": "size",
        "平台生产日均": "consumption_quantity",
    })
    if not period_source.empty:
        period_source["consumption_quantity"] = pd.to_numeric(
            period_source["consumption_quantity"], errors="coerce"
        ).fillna(0) * int(period_days)
        with st.expander(
            f"查看{category}最近{int(period_days)}天颜色尺码生产量",
            expanded=False,
        ):
            st.dataframe(
                _usage_wide_table(period_source),
                hide_index=True,
                width="stretch",
                column_config={
                    "颜色": st.column_config.TextColumn("颜色"),
                    **{
                        size: st.column_config.NumberColumn(
                            size, format="%.0f"
                        )
                        for size in SIZE_COLUMNS
                    },
                },
            )
    st.caption(
        "自定义总日耗会先按当前颜色、尺码占比等比例分配；"
        "如需校正断码或特殊需求，可展开逐项修改。"
    )
    with st.expander("按颜色和尺码微调预测日耗", expanded=True):
        wide = _usage_wide_table(adjusted)
        original_fingerprint = _stable_usage_fingerprint(adjusted)
        fingerprint = original_fingerprint
        edited = st.data_editor(
            wide,
            hide_index=True,
            width="stretch",
            height=fit_table_height(wide),
            disabled=["颜色"],
            key=(
                f"forecast_sku_usage_{category}_{period_days}_"
                f"{custom_daily}_{fingerprint}"
            ),
            column_config={
                "颜色": st.column_config.TextColumn("颜色"),
                **{
                    size: st.column_config.NumberColumn(
                        size, min_value=0.0, step=1.0, format="%.1f"
                    )
                    for size in SIZE_COLUMNS
                },
            },
        )
        adjusted = _usage_long_table(edited)
        customized = customized or (
            _stable_usage_fingerprint(adjusted) != original_fingerprint
        )
        st.metric(
            "微调后预测日耗",
            f"{pd.to_numeric(adjusted['consumption_quantity'], errors='coerce').sum():,.1f} 件",
        )
    applied_daily = pd.to_numeric(
        adjusted.get("consumption_quantity"), errors="coerce"
    ).fillna(0).sum()
    st.success(
        f"当前采用日耗：{applied_daily:,.1f} 件；点货量、缺口、可撑天数和"
        "库存与到货联动均按此数值重新计算。"
    )
    return adjusted, customized


def _stable_usage_fingerprint(model_df):
    columns = ["color", "size", "consumption_quantity"]
    source = pd.DataFrame(model_df).copy()
    if source.empty:
        return 0
    for column in columns:
        if column not in source:
            source[column] = "" if column != "consumption_quantity" else 0
    source["color"] = source["color"].fillna("").astype(str)
    source["size"] = source["size"].fillna("").astype(str)
    source["consumption_quantity"] = pd.to_numeric(
        source["consumption_quantity"], errors="coerce"
    ).fillna(0).astype(float)
    source = source[columns].sort_values(
        ["color", "size", "consumption_quantity"], kind="stable"
    ).reset_index(drop=True)
    return int(pd.util.hash_pandas_object(source, index=False).sum())


def _usage_wide_table(model_df):
    source = pd.DataFrame(model_df).rename(columns={
        "color": "颜色", "size": "尺码",
        "consumption_quantity": "预测日耗",
    })
    if source.empty:
        return pd.DataFrame(columns=["颜色", *SIZE_COLUMNS])
    wide = source.pivot_table(
        index="颜色", columns="尺码", values="预测日耗",
        aggfunc="sum", fill_value=0,
    ).reindex(columns=SIZE_COLUMNS, fill_value=0).reset_index()
    return wide[["颜色", *SIZE_COLUMNS]]


def _usage_long_table(wide_df):
    source = pd.DataFrame(wide_df).copy()
    if source.empty:
        return pd.DataFrame(columns=["color", "size", "consumption_quantity"])
    long = source.melt(
        id_vars=["颜色"], value_vars=SIZE_COLUMNS,
        var_name="size", value_name="consumption_quantity",
    ).rename(columns={"颜色": "color"})
    long["consumption_quantity"] = pd.to_numeric(
        long["consumption_quantity"], errors="coerce"
    ).fillna(0).clip(lower=0)
    return long[long["consumption_quantity"] > 0].reset_index(drop=True)
