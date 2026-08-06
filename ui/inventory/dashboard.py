from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    apply_automatic_daily_previews,
    load_automatic_daily_previews,
)
from db.inventory.dashboard import (
    build_automatic_missing_dates,
    load_daily_completion_status,
    load_inventory_overview,
)
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)
from utils.auth import get_current_operator_name, has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_inventory_dashboard(supabase):
    st.title("库存总结")
    st.caption(
        "集中查看生产库存、耗材库存、货柜安排和每日消耗完成情况。"
    )
    today = datetime.now(NY_TIMEZONE).date()
    _render_overview(supabase, today)
    st.divider()
    automatic_missing_dates = _render_daily_completion(supabase, today)
    st.divider()
    _render_automatic_daily_operation(
        supabase, automatic_missing_dates
    )


def _render_overview(supabase, today):
    st.subheader("库存总览")
    try:
        overview = load_inventory_overview(supabase, today)
    except Exception as error:
        st.error(f"库存总览加载失败：{error}")
        return
    production, consumables, containers = st.columns(3)
    with production.container(border=True):
        st.markdown("#### 生产库存")
        left, right = st.columns(2)
        left.metric("库存件数", f"{overview['production_units']:,}")
        right.metric("缺货 SKU", overview["zero_stock_skus"])
        st.caption(f"共 {overview['production_skus']:,} 个 SKU")
        st.page_link("pages/4_库存.py", label="查看生产库存 →")
    with consumables.container(border=True):
        st.markdown("#### 耗材库存")
        left, right = st.columns(2)
        left.metric("启用 SKU", overview["consumable_skus"])
        right.metric("低库存", overview["low_consumable_skus"])
        st.caption("低库存按各耗材安全库存判断")
        st.page_link("pages/9_耗材库存.py", label="查看耗材库存 →")
    with containers.container(border=True):
        st.markdown("#### 货柜安排")
        first, second, third = st.columns(3)
        first.metric("在途", overview["in_transit_containers"])
        second.metric("7天到柜", overview["arriving_containers"])
        third.metric("延迟", overview["delayed_containers"])
        st.page_link("pages/5_货柜安排.py", label="查看货柜安排 →")


def _render_daily_completion(supabase, today):
    heading, control = st.columns([4, 1])
    heading.subheader("每日库存扣减完成情况")
    lookback_days = control.selectbox(
        "检查范围", [7, 14, 30], index=0,
        format_func=lambda value: f"最近 {value} 天",
        key="inventory_dashboard_lookback",
    )
    try:
        summary, completed, start_date = load_daily_completion_status(
            supabase, today, lookback_days
        )
    except Exception as error:
        st.error(f"每日出库状态加载失败：{error}")
        return {}
    missing = int(summary["待处理天数"].sum())
    if missing:
        st.warning(f"四类出库合计还有 {missing} 个日期需要处理。")
    else:
        st.success(f"最近 {lookback_days} 天的四类出库全部完成。")
    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        column_config={
            "已完成天数": st.column_config.ProgressColumn(
                "已完成天数", min_value=0, max_value=lookback_days,
                format="%d 天",
            ),
            "检查天数": None,
            "待处理天数": st.column_config.NumberColumn(format="%d 天"),
        },
    )
    st.caption(
        "人工项目显示需要补录的实际出库；系统项目显示需要读取来源并扣减的日期。"
    )
    links = st.columns(2)
    links[0].page_link(
        "pages/4_库存.py", label="补录黑白短袖出库 →"
    )
    links[1].page_link(
        "pages/9_耗材库存.py", label="补录 DTF 耗材出库 →"
    )
    return build_automatic_missing_dates(
        completed, start_date, today
    )


def _render_automatic_daily_operation(supabase, missing_dates):
    st.subheader("系统数据一键消耗库存")
    st.caption(
        "当前统一处理彩色短袖生产数据和 UV Google Sheets；"
        "以后新增自动来源会继续加入这里。"
    )
    if not missing_dates:
        st.success("彩色短袖和 UV 在当前检查范围内均已完成扣减。")
        return
    options = list(missing_dates)
    operation_date = st.selectbox(
        "待补扣日期",
        options,
        format_func=lambda value: (
            f"{value:%Y-%m-%d}｜{missing_dates[value]}"
        ),
        key="inventory_dashboard_auto_missing_date",
        help="这里只显示彩色短袖或 UV 尚未扣减的日期。",
    )
    spreadsheet = render_uv_spreadsheet_selector(
        key="inventory_dashboard_uv_spreadsheet"
    )
    state_key = "inventory_dashboard_auto_previews"
    identity_key = "inventory_dashboard_auto_preview_identity"
    identity = (operation_date.isoformat(), spreadsheet["id"])
    if st.button(
        "读取彩色短袖与 UV 数据",
        type="secondary",
        width="stretch",
        key="inventory_dashboard_auto_load",
    ):
        try:
            sheets_client = google_sheets_client()
        except Exception:
            sheets_client = None
        previews = load_automatic_daily_previews(
            supabase,
            operation_date,
            sheets_client,
            spreadsheet["id"],
        )
        st.session_state[state_key] = previews
        st.session_state[identity_key] = identity

    previews = st.session_state.get(state_key)
    if (
        not previews
        or st.session_state.get(identity_key) != identity
    ):
        return
    ready = []
    columns = st.columns(len(AUTOMATIC_DAILY_FLOWS))
    for column, flow in zip(columns, AUTOMATIC_DAILY_FLOWS):
        preview = previews[flow.code]
        with column.container(border=True):
            st.markdown(f"#### {flow.label}")
            if preview.state == "completed":
                st.success(f"已扣减 {preview.quantity:,} 件")
            elif preview.state == "ready":
                ready.append(flow)
                st.metric("本次预计扣减", f"{preview.quantity:,} 件")
                st.caption("已读取，等待统一确认")
            elif preview.state == "blocked":
                st.error("存在阻止扣减的问题")
                st.caption(preview.message)
            elif preview.state == "error":
                st.error("来源读取失败")
                st.caption(preview.message)
            else:
                st.info(preview.message)
            if not preview.rows.empty:
                with st.expander("查看 SKU 明细"):
                    st.dataframe(
                        preview.rows, hide_index=True, width="stretch"
                    )
    if not ready:
        st.info("当前没有需要扣减的系统数据。")
        return
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能扣减库存。")
        return
    total = sum(previews[flow.code].quantity for flow in ready)
    confirmed = st.checkbox(
        f"我已核对以上数据，确认共扣减 {total:,} 件",
        key="inventory_dashboard_auto_confirm",
    )
    if not st.button(
        "确认并扣减全部系统库存",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key="inventory_dashboard_auto_apply",
    ):
        return
    results, errors = apply_automatic_daily_previews(
        supabase,
        operation_date,
        previews,
        get_current_operator_name(),
    )
    labels = {flow.code: flow.label for flow in AUTOMATIC_DAILY_FLOWS}
    if results:
        details = "；".join(
            f"{labels[code]} {quantity:,} 件"
            for code, quantity in results.items()
        )
        st.session_state["inventory_dashboard_saved_message"] = (
            f"系统库存扣减完成：{details}"
        )
    if errors:
        st.session_state["inventory_dashboard_error_message"] = "；".join(
            f"{labels[code]}：{message}"
            for code, message in errors.items()
        )
    st.session_state.pop(state_key, None)
    st.session_state.pop(identity_key, None)
    st.rerun()
