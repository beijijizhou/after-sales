import streamlit as st

from ui.inventory.i18n import t


FORECAST_COLUMNS = [
    "颜色", "库存基准日期", "当前日期", "最低剩余天数",
    "预计最早耗尽日期", "低于14天尺码", "到货前需覆盖天数",
    "到货前缺口总数", "到货前缺口尺码",
]


def render_reorder_forecast_table(forecast_df):
    forecast_df = forecast_df[
        [column for column in FORECAST_COLUMNS if column in forecast_df.columns]
    ]
    display_df = forecast_df.style.apply(highlight_forecast_risk, axis=1)
    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "最低剩余天数": st.column_config.NumberColumn(
                t("最低剩余天数"), format="%d"
            ),
            "库存基准日期": st.column_config.DateColumn(
                t("库存基准日期"), format="YYYY-MM-DD"
            ),
            "当前日期": st.column_config.DateColumn(
                t("当前日期"), format="YYYY-MM-DD"
            ),
            "预计最早耗尽日期": st.column_config.DateColumn(
                t("预计最早耗尽日期"), format="YYYY-MM-DD"
            ),
            "低于14天尺码": st.column_config.TextColumn(t("低于14天尺码")),
            "到货前需覆盖天数": st.column_config.NumberColumn(
                t("到货前需覆盖天数"), format="%d"
            ),
            "到货前缺口总数": st.column_config.NumberColumn(
                t("到货前缺口总数"), format="%d"
            ),
            "到货前缺口尺码": st.column_config.TextColumn(t("到货前缺口尺码")),
        },
    )


def highlight_forecast_risk(row):
    styles = []
    for column in row.index:
        if is_below_days(row.get("最低剩余天数"), 14) and column in [
            "最低剩余天数", "低于14天尺码",
        ]:
            styles.append("background-color: #ffe0e0; color: #8a0000; font-weight: 700;")
        elif is_positive(row.get("到货前缺口总数")) and column in [
            "到货前缺口总数", "到货前缺口尺码",
        ]:
            styles.append("background-color: #fff1cc; color: #7a4a00; font-weight: 700;")
        else:
            styles.append("")
    return styles


def is_below_days(value, days):
    try:
        return float(value) < days
    except (TypeError, ValueError):
        return False


def is_positive(value):
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
