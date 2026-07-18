import streamlit as st

from automation.production import (
    PLATFORMS_BY_DEPARTMENT,
    PRODUCTION_DEPARTMENTS,
)
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from utils.erp import (
    apply_production_scope,
    build_color_size_summary,
    build_daily_summary,
    build_material_summary,
    build_platform_summary,
    build_status_summary,
)
from utils.erp.catalog import normalize_production_catalog
from utils.erp.material import normalize_production_material
from utils.erp.summary import SCOPE_OPTIONS
from ui.production_data.controls import render_production_filters
from ui.production_data.fetch import fetch_and_store_production_data


def render_production_data_page():
    st.title("生产数据")
    st.caption("从生产平台自动获取并汇总指定日期的生产数据。")
    department_col, platform_col = st.columns(2)
    with department_col:
        department = st.selectbox(
            "部门",
            PRODUCTION_DEPARTMENTS,
            index=0,
        )
    department_platforms = PLATFORMS_BY_DEPARTMENT[department]
    platforms = (
        (ALL_CLOTHING_PLATFORMS, *department_platforms)
        if department == "DTF"
        else department_platforms
    )
    with platform_col:
        platform = st.selectbox(
            "生产平台",
            platforms,
            disabled=not platforms,
            key=f"production_platform_{department}",
        )
        if platforms:
            st.caption(f"已接入平台：{'、'.join(department_platforms)}")
    selected_range, start_hour, end_hour, submitted = (
        render_production_filters(platform)
    )
    if submitted:
        fetch_and_store_production_data(
            platform,
            *selected_range,
            start_hour=start_hour,
            end_hour=end_hour,
        )

    if not platform:
        st.info(f"{department} 部门暂未接入生产数据平台。")
        return

    platform_data = st.session_state.get("production_data_by_platform", {})
    source = platform_data.get(platform)
    if source is None:
        st.info(f"尚未获取{platform}生产数据。")
        return
    source_df = normalize_production_material(
        normalize_production_catalog(source["data"])
    )
    source_file = source["file"]
    st.success(f"已读取：{platform} / {source_file}")

    scope = st.segmented_control(
        "统计口径", options=SCOPE_OPTIONS, default=SCOPE_OPTIONS[0]
    )
    department_df = source_df[source_df["部门"] == department]
    report_df = apply_production_scope(
        department_df,
        scope or SCOPE_OPTIONS[0],
    )
    canceled_quantity = int(department_df.loc[
        department_df["生产项状态"] == "已取消", "数量"
    ].sum())

    is_summary = (
        "数据口径" in report_df.columns
        and not report_df.empty
        and report_df["数据口径"].eq("汇总").all()
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "模板组合" if is_summary else "生产项",
        _unique_platform_count(report_df, "生产项编码"),
    )
    col2.metric(
        "商品模板" if is_summary else "生产单",
        _unique_platform_count(report_df, "生产单号"),
    )
    col3.metric("需求件数", int(report_df["数量"].sum()))
    col4.metric("已取消件数", canceled_quantity)
    _render_date_range(report_df)

    platform_tab, color_tab, material_tab, daily_tab, status_tab, detail_tab = st.tabs([
        "平台汇总",
        _specification_tab_label(report_df),
        "材质", "每日数据", "生产状态", "生产项明细",
    ])
    with platform_tab:
        _render_table(build_platform_summary(report_df))
    with color_tab:
        _render_table(build_color_size_summary(report_df))
    with material_tab:
        _render_table(build_material_summary(report_df))
    with daily_tab:
        _render_table(build_daily_summary(report_df))
    with status_tab:
        _render_table(build_status_summary(department_df))
    with detail_tab:
        _render_table(report_df, height=520)
def _render_date_range(df):
    created = df["创建时间"].dropna()
    if created.empty:
        return
    st.caption(
        f"创建时间范围：{created.min():%Y-%m-%d %H:%M} 至 "
        f"{created.max():%Y-%m-%d %H:%M}"
    )


def _render_table(df, height=None):
    display_df = df.copy()
    for column in ["尺码", "型号"]:
        if column in display_df.columns and _is_blank_column(display_df[column]):
            display_df = display_df.drop(columns=column)
    config = {
        column: st.column_config.NumberColumn(column, format="%d")
        for column in ["生产项数", "生产单数", "件数", "合计"]
        if column in display_df.columns
    }
    options = {
        "hide_index": True,
        "width": "stretch",
        "column_config": config,
    }
    if height is not None:
        options["height"] = height
    st.dataframe(display_df, **options)


def _specification_tab_label(df):
    has_sizes = "尺码" in df and not _is_blank_column(df["尺码"])
    has_models = "型号" in df and not _is_blank_column(df["型号"])
    if has_sizes and has_models:
        return "颜色尺码/型号"
    return "颜色尺码" if has_sizes else "颜色型号"


def _is_blank_column(series):
    return series.fillna("").astype(str).str.strip().eq("").all()


def _unique_platform_count(df, column):
    if "运营商" not in df.columns:
        return df[column].nunique()
    return len(df[["运营商", column]].drop_duplicates())
