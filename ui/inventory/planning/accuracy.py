import streamlit as st

from db.inventory.planning.consumption_comparison import (
    build_model_accuracy_summary,
)


def render_model_accuracy_summary(comparison_df, baseline_label=None):
    accuracy = build_model_accuracy_summary(comparison_df)
    if baseline_label and not accuracy.empty:
        accuracy["模型"] = accuracy["模型"].replace({
            "15,000模型": baseline_label,
        })
    if accuracy.empty:
        st.info("平台生产数据不足，暂时无法判断模型偏差。")
        return

    best = accuracy.iloc[0]
    st.success(
        f"以最新平台生产数据为参照，当前最接近的是"
        f"「{best['模型']}」，整体偏差 {best['与平台数据偏差']:.1f}%。"
    )
    st.caption(
        "平台生产数据代表当前需求；仓库出库可能存在录入延迟。"
        "三模型平均适合作为稳健参考，不代表真实消耗。"
    )
    st.dataframe(
        accuracy,
        hide_index=True,
        width="stretch",
        column_config={
            "与平台数据偏差": st.column_config.NumberColumn(
                "与平台数据偏差", format="%.1f%%"
            ),
            "匹配度": st.column_config.ProgressColumn(
                "匹配度", min_value=0, max_value=100, format="%.1f%%"
            ),
        },
    )
