import pandas as pd
import streamlit as st

from ui.inventory.i18n import t


STATUS_ORDER = {"爆单": 0, "持续偏高": 1, "观察": 2, "正常": 3}


def render_demand_anomaly_monitor(anomaly_df):
    st.subheader(t("异常消耗监控"))
    st.caption(t("异常监控说明"))
    if anomaly_df.empty:
        st.info(t("暂无足够的每日出库数据"))
        return

    anomaly_df = anomaly_df[anomaly_df["状态"] != "正常"].copy()
    if anomaly_df.empty:
        st.success(t("当前没有异常消耗"))
        return

    active_count = int(anomaly_df["状态"].isin(["爆单", "持续偏高"]).sum())
    watch_count = int((anomaly_df["状态"] == "观察").sum())
    col1, col2 = st.columns(2)
    col1.metric(t("已启用风险日耗"), active_count)
    col2.metric(t("单日异常观察"), watch_count)

    display_df = anomaly_df.copy()
    display_df["_order"] = display_df["状态"].map(STATUS_ORDER).fillna(99)
    display_df = display_df.sort_values(
        ["_order", "风险剩余天数", "颜色", "尺码"], na_position="last"
    ).drop(columns=["_order"])
    display_df["状态"] = display_df["状态"].map(t)
    display_df["异常类型"] = display_df["异常类型"].map(t)
    styled_df = display_df.style.apply(highlight_anomaly, axis=1)

    st.dataframe(
        styled_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "尺码": st.column_config.TextColumn(t("尺码")),
            "当前库存": st.column_config.NumberColumn(t("当前库存"), format="%d"),
            "最近出库日期": st.column_config.DateColumn(t("最近出库日期")),
            "基础日耗": st.column_config.NumberColumn(t("基础日耗"), format="%d"),
            "最近出库": st.column_config.NumberColumn(t("最近出库"), format="%d"),
            "近2次平均": st.column_config.NumberColumn(t("近2次平均"), format="%d"),
            "近3次平均": st.column_config.NumberColumn(t("近3次平均"), format="%d"),
            "消耗倍数": st.column_config.NumberColumn(t("消耗倍数"), format="%.2f"),
            "占比偏离": st.column_config.NumberColumn(t("占比偏离"), format="%.2f"),
            "异常类型": st.column_config.TextColumn(t("异常类型")),
            "状态": st.column_config.TextColumn(t("状态")),
            "风险日耗": st.column_config.NumberColumn(t("风险日耗"), format="%d"),
            "风险剩余天数": st.column_config.NumberColumn(t("风险剩余天数"), format="%d"),
        },
    )


def highlight_anomaly(row):
    status = row.get("状态")
    if status == t("爆单"):
        color = "background-color: #ffd6d6; color: #8a0000; font-weight: 700;"
    elif status == t("持续偏高"):
        color = "background-color: #ffe7c2; color: #7a3d00; font-weight: 700;"
    elif status == t("观察"):
        color = "background-color: #fff4cc; color: #6b5200;"
    else:
        color = ""
    return [color if column in ["状态", "风险日耗", "风险剩余天数"] else "" for column in row.index]
