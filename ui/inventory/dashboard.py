from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    apply_automatic_daily_batch_previews,
    build_automatic_daily_batch_summary,
    load_automatic_daily_batch_previews,
)
from db.inventory.dashboard import (
    build_automatic_missing_dates,
    build_today_completion_status,
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
    saved_message = st.session_state.pop(
        "inventory_dashboard_saved_message", None
    )
    error_message = st.session_state.pop(
        "inventory_dashboard_error_message", None
    )
    if saved_message:
        st.success(saved_message)
    if error_message:
        st.error(error_message)
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
    st.subheader("每日库存扣减完成情况")
    try:
        summary, completed, start_date = load_daily_completion_status(
            supabase, today
        )
    except Exception as error:
        st.error(f"每日出库状态加载失败：{error}")
        return {}
    missing = int(summary["待处理天数"].sum())
    history_end = today - timedelta(days=1)
    check_days = max((history_end - start_date).days + 1, 0)
    if check_days:
        st.caption(
            f"补录统计：{start_date:%Y-%m-%d} 至 "
            f"{history_end:%Y-%m-%d}｜共 {check_days} 个已结束日期"
        )
    else:
        st.caption("补录统计：暂无已经结束的日期")
    if missing:
        st.warning(
            f"四类出库合计还有 {missing} 个日期/项目需要处理。"
        )
    else:
        st.success(
            f"截至 {history_end:%Y-%m-%d} 的四类出库全部完成。"
        )
    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        column_config={
            "已完成天数": st.column_config.ProgressColumn(
                "已完成天数", min_value=0, max_value=max(check_days, 1),
                format="%d 天",
            ),
            "检查天数": None,
            "待处理天数": st.column_config.NumberColumn(format="%d 天"),
        },
    )
    st.caption(
        "人工项目显示需要补录的实际出库；系统项目显示需要读取来源并扣减的日期。"
    )
    today_status = build_today_completion_status(completed, today)
    completed_today = "、".join(today_status["completed"]) or "无"
    pending_today = "、".join(today_status["pending"]) or "无"
    st.info(
        f"今日 {today:%m/%d} 正在进行：已完成 {completed_today}；"
        f"尚未完成 {pending_today}。今天尚未结束，未完成项目属于正常进度，"
        "不计入补录。"
    )
    links = st.columns(2)
    links[0].page_link(
        "pages/4_库存.py", label="补录黑白短袖出库 →"
    )
    links[1].page_link(
        "pages/9_耗材库存.py", label="补录 DTF 耗材出库 →"
    )
    return build_automatic_missing_dates(
        completed, start_date, history_end
    )


def _render_automatic_daily_operation(supabase, missing_dates):
    st.subheader("系统出库一键补录")
    st.caption(
        "当前统一处理彩色短袖生产数据和 UV Google Sheets；"
        "以后新增自动来源会继续加入这里。"
    )
    if not missing_dates:
        st.success("彩色短袖和 UV 在当前检查范围内均已完成扣减。")
        return
    options = sorted(missing_dates)
    st.caption(
        "待补扣日期：" + "；".join(
            f"{value:%Y-%m-%d}（{missing_dates[value]}）"
            for value in options
        )
    )
    spreadsheet = render_uv_spreadsheet_selector(
        key="inventory_dashboard_uv_spreadsheet"
    )
    state_key = "inventory_dashboard_auto_previews"
    identity_key = "inventory_dashboard_auto_preview_identity"
    identity = (
        tuple(
            (value.isoformat(), missing_dates[value])
            for value in options
        ),
        spreadsheet["id"],
    )
    if st.button(
        "一键读取全部待补日期",
        type="secondary",
        width="stretch",
        key="inventory_dashboard_auto_load",
    ):
        try:
            sheets_client = google_sheets_client()
        except Exception:
            sheets_client = None
        previews = load_automatic_daily_batch_previews(
            supabase,
            missing_dates,
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
    state_labels = {
        "ready": "待确认", "completed": "已完成",
        "blocked": "存在问题", "error": "读取失败",
        "no_data": "无数据",
    }
    summary = build_automatic_daily_batch_summary(previews)
    display_summary = summary.copy()
    display_summary["状态"] = display_summary["状态"].map(
        state_labels
    ).fillna(display_summary["状态"])
    st.subheader("批量补扣预览")
    st.dataframe(
        display_summary,
        hide_index=True,
        width="stretch",
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            "预计扣减": st.column_config.NumberColumn(
                "预计扣减", format="%d 件"
            ),
            "来源总量": st.column_config.NumberColumn(
                "来源总量", format="%d 件"
            ),
            "待核对差额": st.column_config.NumberColumn(
                "待核对差额", format="%d 件"
            ),
            "说明": st.column_config.TextColumn("说明", width="large"),
        },
    )
    ready = [
        (movement_date, flow, previews[movement_date].get(flow.code))
        for movement_date in sorted(previews)
        for flow in AUTOMATIC_DAILY_FLOWS
        if previews[movement_date].get(flow.code) is not None
        and previews[movement_date][flow.code].state == "ready"
    ]
    details = [
        (movement_date, flow, previews[movement_date].get(flow.code))
        for movement_date in sorted(previews)
        for flow in AUTOMATIC_DAILY_FLOWS
        if previews[movement_date].get(flow.code) is not None
        and (
            not previews[movement_date][flow.code].rows.empty
            or previews[movement_date][flow.code].source_rows is not None
        )
    ]
    for movement_date, flow, preview in details:
        with st.expander(
            f"{movement_date:%Y-%m-%d}｜{flow.label}｜"
            f"预计扣减 {preview.quantity:,} 件"
        ):
            if preview.source_rows is not None:
                st.markdown("**平台来源核对**")
                st.caption(
                    f"原始生产 {preview.source_quantity:,} 件｜"
                    f"可扣库存 {preview.quantity:,} 件｜"
                    f"待核对 {preview.unresolved_quantity:,} 件"
                )
                st.dataframe(
                    preview.source_rows, hide_index=True, width="stretch",
                    column_config={
                        "原始生产件数": st.column_config.NumberColumn(
                            format="%d 件"
                        ),
                        "生产记录数": st.column_config.NumberColumn(
                            format="%d 条"
                        ),
                    },
                )
                st.markdown("**SKU 库存匹配**")
            st.dataframe(preview.rows, hide_index=True, width="stretch")
    if not ready:
        st.info("当前没有需要扣减的系统数据。")
        return
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能扣减库存。")
        return
    total = sum(preview.quantity for _, _, preview in ready)
    confirmed = st.checkbox(
        f"我已核对 {len(ready)} 个日期/项目，确认共扣减 {total:,} 件",
        key="inventory_dashboard_auto_confirm",
    )
    if not st.button(
        "一键补扣全部已预览库存",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key="inventory_dashboard_auto_apply",
    ):
        return
    results, errors = apply_automatic_daily_batch_previews(
        supabase,
        previews,
        get_current_operator_name(),
    )
    labels = {flow.code: flow.label for flow in AUTOMATIC_DAILY_FLOWS}
    if results:
        details = "；".join(
            f"{movement_date:%m/%d} {labels[code]} {quantity:,} 件"
            for (movement_date, code), quantity in results.items()
        )
        st.session_state["inventory_dashboard_saved_message"] = (
            f"系统库存扣减完成：{details}"
        )
    if errors:
        st.session_state["inventory_dashboard_error_message"] = "；".join(
            f"{movement_date:%m/%d} {labels[code]}：{message}"
            for (movement_date, code), message in errors.items()
        )
    st.session_state.pop(state_key, None)
    st.session_state.pop(identity_key, None)
    st.rerun()
