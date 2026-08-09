from datetime import date

import streamlit as st

from automation.sync.uv_sheet_inventory import load_monthly_sku_summary
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)


def render_uv_monthly_summary(default_month=None):
    st.subheader("UV Google Sheets 月度按 SKU 汇总")
    st.caption(
        "按 Google Sheets 每日工作表 A:K 明细读取整月数据；"
        "只统计材质非空、数量有效、进度为“完成”的生产行。"
    )
    spreadsheet = render_uv_spreadsheet_selector(
        key="production_data_uv_monthly_spreadsheet"
    )
    default_value = default_month or date.today().replace(day=1)
    month_value = st.date_input(
        "汇总月份",
        value=default_value,
        max_value=date.today().replace(day=1),
        key="production_data_uv_monthly_month",
    )
    if st.button(
        "生成月度按 SKU 汇总",
        key="production_data_uv_monthly_submit",
        type="primary",
    ):
        with st.spinner("正在读取 UV Google Sheets 月度汇总..."):
            daily_df, sku_df, missing_dates = load_monthly_sku_summary(
                google_sheets_client(),
                spreadsheet["id"],
                month_value.year,
                month_value.month,
            )
        st.session_state["uv_monthly_summary_result"] = {
            "daily_df": daily_df,
            "sku_df": sku_df,
            "missing_dates": missing_dates,
            "month": month_value,
            "spreadsheet": spreadsheet,
        }

    result = st.session_state.get("uv_monthly_summary_result")
    if not result or result["month"] != month_value:
        return

    daily_df = result["daily_df"]
    sku_df = result["sku_df"]
    missing_dates = result["missing_dates"]
    st.caption(
        f"数据表：{result['spreadsheet']['name']}｜"
        f"月份：{month_value:%Y-%m}"
    )
    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("已读取工作表", len(daily_df))
    metric2.metric("SKU 数", len(sku_df))
    metric3.metric(
        "月总件数",
        f"{int(sku_df['total_quantity'].sum()) if not sku_df.empty else 0:,}",
    )
    if missing_dates:
        st.warning(
            "缺失工作表："
            + "、".join(day.date().strftime("%m%d") for day in missing_dates)
        )
    st.dataframe(
        sku_df,
        hide_index=True,
        width="stretch",
        column_config={
            "total_quantity": st.column_config.NumberColumn(format="%d"),
        },
    )
    with st.expander("查看每日明细", expanded=False):
        st.dataframe(
            daily_df,
            hide_index=True,
            width="stretch",
            column_config={
                "date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "total_quantity": st.column_config.NumberColumn(format="%d"),
            },
        )
    st.download_button(
        "下载按 SKU 汇总 CSV",
        sku_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"uv_production_{month_value:%Y-%m}_sku_totals.csv",
        mime="text/csv",
        key="production_data_uv_monthly_download_sku",
    )
    st.download_button(
        "下载每日汇总 CSV",
        daily_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"uv_production_{month_value:%Y-%m}_daily_totals.csv",
        mime="text/csv",
        key="production_data_uv_monthly_download_daily",
    )
