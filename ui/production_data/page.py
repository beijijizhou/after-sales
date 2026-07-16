from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from automation.playwright.haloo import (
    DIAGNOSTIC_PATH,
    ERP_PLATFORM_NAMES,
    HalooLoginRequired,
    download_production_workbook,
)
from utils.erp import (
    apply_production_scope,
    build_color_size_summary,
    build_daily_summary,
    build_material_summary,
    build_status_summary,
    parse_production_workbook,
)
from utils.erp.summary import SCOPE_OPTIONS


def render_production_data_page():
    st.title("生产数据")
    st.caption("从已登录的蜂鸟 ERP 工厂端自动导出并读取生产项 Excel。")
    platform = st.selectbox("ERP 平台", ERP_PLATFORM_NAMES)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    selected_range = st.date_input(
        "生产时间",
        value=(today, today),
        max_value=today,
    )
    has_date_range = len(selected_range) == 2
    if st.button(
        "获取生产数据",
        type="primary",
        width="stretch",
        disabled=not has_date_range,
    ):
        _fetch_production_data(platform, *selected_range)
    if not has_date_range:
        st.info("请选择开始日期和结束日期。")

    platform_data = st.session_state.get("production_data_by_platform", {})
    source = platform_data.get(platform)
    if source is None:
        st.info(f"尚未获取{platform}生产数据。")
        return
    source_df = source["data"]
    source_file = source["file"]
    st.success(f"已读取：{platform} / {source_file}")

    scope = st.segmented_control(
        "统计口径", options=SCOPE_OPTIONS, default=SCOPE_OPTIONS[0]
    )
    report_df = apply_production_scope(source_df, scope or SCOPE_OPTIONS[0])
    canceled_quantity = int(source_df.loc[
        source_df["生产项状态"] == "已取消", "数量"
    ].sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("生产项", report_df["生产项编码"].nunique())
    col2.metric("生产单", report_df["生产单号"].nunique())
    col3.metric("需求件数", int(report_df["数量"].sum()))
    col4.metric("已取消件数", canceled_quantity)
    _render_date_range(report_df)

    color_tab, material_tab, daily_tab, status_tab, detail_tab = st.tabs([
        "颜色尺码", "材质", "每日数据", "生产状态", "生产项明细",
    ])
    with color_tab:
        _render_table(build_color_size_summary(report_df))
    with material_tab:
        _render_table(build_material_summary(report_df))
    with daily_tab:
        _render_table(build_daily_summary(report_df))
    with status_tab:
        _render_table(build_status_summary(source_df))
    with detail_tab:
        _render_table(report_df, height=520)


def _fetch_production_data(platform, start_date, end_date):
    status = st.status("正在准备生产数据同步...", expanded=True)

    def report_progress(message):
        status.write(message)

    try:
        file_path = download_production_workbook(
            start_date,
            end_date,
            report_progress=report_progress,
            platform=platform,
        )
        status.write("正在解析 Excel 并核对字段")
        source_df = parse_production_workbook(file_path.read_bytes())
        platform_data = dict(
            st.session_state.get("production_data_by_platform", {})
        )
        platform_data[platform] = {
            "data": source_df,
            "file": file_path.name,
        }
        st.session_state["production_data_by_platform"] = platform_data
        status.update(
            label=f"生产数据获取完成：{file_path.name}",
            state="complete",
            expanded=False,
        )
        st.toast("生产数据获取完成")
    except HalooLoginRequired as error:
        status.update(label=f"等待登录：{error}", state="error", expanded=True)
        st.warning(str(error))
    except Exception as error:
        status.update(label=f"获取失败：{error}", state="error", expanded=True)
        st.error(f"生产数据获取失败：{error}")
        if DIAGNOSTIC_PATH.exists():
            st.caption("已记录当前页面控件，便于校准自动化流程。")


def _render_date_range(df):
    created = df["创建时间"].dropna()
    if created.empty:
        return
    st.caption(
        f"创建时间范围：{created.min():%Y-%m-%d %H:%M} 至 "
        f"{created.max():%Y-%m-%d %H:%M}"
    )


def _render_table(df, height=None):
    config = {
        column: st.column_config.NumberColumn(column, format="%d")
        for column in ["生产项数", "生产单数", "件数", "合计"]
        if column in df.columns
    }
    options = {
        "hide_index": True,
        "width": "stretch",
        "column_config": config,
    }
    if height is not None:
        options["height"] = height
    st.dataframe(df, **options)
