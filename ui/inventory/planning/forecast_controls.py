import pandas as pd
import streamlit as st

from db.inventory.planning.consumption_comparison import (
    FORECAST_SOURCE_WEIGHTS,
    normalize_forecast_weights,
)
from ui.inventory.i18n import t


WEIGHT_FIELDS = [
    ("15,000模型日耗", "1.5万模型占比", "15,000模型"),
    ("平台生产日均", "平台生产占比", "平台生产模型"),
    ("仓库出库日均", "仓库出库占比", "仓库出库模型"),
]


def render_forecast_model_controls():
    st.subheader(t("点货预测参数"))
    columns = st.columns(3)
    entered = {}
    for column, (field, label, _) in zip(columns, WEIGHT_FIELDS):
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
            t("数据来源"): t(source_label),
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
