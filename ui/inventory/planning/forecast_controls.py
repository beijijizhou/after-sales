import pandas as pd
import streamlit as st

from db.inventory.planning.consumption_comparison import (
    FORECAST_SOURCE_WEIGHTS,
    normalize_forecast_weights,
    scale_forecast_daily_total,
)
from db.inventory.core.constants import SIZE_COLUMNS
from ui.inventory.i18n import t


WEIGHT_FIELDS = [
    ("15,000模型日耗", "1.5万模型占比", "15,000模型"),
    ("平台生产日均", "平台生产占比", "平台生产模型"),
    ("仓库出库日均", "仓库出库占比", "仓库出库模型"),
]


def render_forecast_model_controls(order_quantity=15000):
    st.subheader(t("点货预测参数"))
    columns = st.columns(3)
    entered = {}
    for column, (field, label, _) in zip(columns, WEIGHT_FIELDS):
        if field == "15,000模型日耗":
            label = f"{int(order_quantity):,}订单模型占比"
        entered[field] = column.number_input(
            t(label),
            min_value=0,
            max_value=100,
            value=int(FORECAST_SOURCE_WEIGHTS[field] * 100),
            step=5,
            key=f"forecast_weight_{field}",
        )

    total = sum(entered.values())
    normalized = normalize_forecast_weights(entered)
    if total == 0:
        st.warning(t("占比不能全部为 0，当前使用默认占比。"))
    elif total != 100:
        st.info(
            t("输入占比合计为 {total}%，系统已自动归一化为 100%。").format(
                total=total
            )
        )

    display = pd.DataFrame([
        {
            t("数据来源"): (
                f"{int(order_quantity):,}订单模型"
                if field == "15,000模型日耗" else t(source_label)
            ),
            t("输入占比"): f"{entered[field]}%",
            t("实际占比"): f"{normalized[field] * 100:.1f}%",
            t("参考顺序"): index,
        }
        for index, (field, _, source_label) in enumerate(
            WEIGHT_FIELDS, start=1
        )
    ])
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption(
        t("最终预测日耗 = 各来源日耗 × 实际占比之和。")
    )
    if st.button(t("恢复默认占比"), key="reset_forecast_weights"):
        for field, _, _ in WEIGHT_FIELDS:
            st.session_state[f"forecast_weight_{field}"] = int(
                FORECAST_SOURCE_WEIGHTS[field] * 100
            )
        st.rerun()
    return normalized


def render_forecast_calculation(
    comparison_df,
    forecast_model_df,
    platform_days,
    platform_start,
    platform_end,
):
    with st.expander(t("查看预测计算明细")):
        if platform_days:
            st.caption(
                f"{t('平台生产数据')}：{platform_start} 至 "
                f"{platform_end}｜{platform_days} {t('天')}"
            )
        else:
            st.warning(t("暂无完整平台生产数据，平台占比将自动重新分配。"))
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
            "颜色", "尺码", "15,000模型日耗", "平台生产日均",
            "仓库出库日均", "最终预测日耗",
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
):
    source = pd.DataFrame(model_df).copy()
    base_daily = pd.to_numeric(
        source.get("consumption_quantity"), errors="coerce"
    ).fillna(0).sum()
    source_fingerprint = int(pd.util.hash_pandas_object(
        source[[
            column for column in ["color", "size", "consumption_quantity"]
            if column in source
        ]], index=True
    ).sum()) if not source.empty else 0
    metrics = st.columns(3)
    metrics[0].metric(
        f"{category}最近{int(period_days)}天生产量",
        f"{period_total:,.0f} 件",
    )
    metrics[1].metric("模型日耗", f"{base_daily:,.1f} 件")
    custom_key = (
        f"forecast_custom_daily_total_{category}_{period_days}_"
        f"{source_fingerprint}"
    )
    custom_daily = metrics[2].number_input(
        "自定义预测日耗",
        min_value=0,
        max_value=1000000,
        value=max(int(round(base_daily)), 0),
        step=max(int(round(base_daily * 0.05)), 1),
        key=custom_key,
        help="默认等于消耗模型日耗；修改后点货量、缺口和货柜联动会同步重算。",
    )
    adjusted = scale_forecast_daily_total(source, custom_daily)
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
    with st.expander("按颜色和尺码微调预测日耗", expanded=False):
        wide = _usage_wide_table(adjusted)
        fingerprint = int(pd.util.hash_pandas_object(
            wide, index=True
        ).sum()) if not wide.empty else 0
        edited = st.data_editor(
            wide,
            hide_index=True,
            width="stretch",
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
        st.metric(
            "微调后预测日耗",
            f"{pd.to_numeric(adjusted['consumption_quantity'], errors='coerce').sum():,.1f} 件",
        )
    return adjusted


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
