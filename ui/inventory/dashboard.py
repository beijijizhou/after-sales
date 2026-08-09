from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    COLORED_FAST_PLATFORM_SCOPE,
    apply_automatic_daily_batch_previews,
    build_automatic_daily_batch_summary,
    load_automatic_daily_batch_previews,
)
from automation.sync.daily import (
    COLORED_PRIMARY_PLATFORMS,
    sync_production_day,
)
from db.inventory.dashboard import (
    build_automatic_missing_dates,
    build_daily_operation_table,
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
    _render_daily_completion(supabase, today)


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
    st.subheader("每日库存扣减")
    st.caption(
        "统一查看历史补录、今日进度，并处理彩色短袖和 UV 的系统扣减。"
    )
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
    automatic_missing_dates = build_automatic_missing_dates(
        completed, start_date, history_end
    )
    requested_flow = _render_completion_overview(
        summary, completed, today, start_date,
        history_end, check_days, missing,
    )
    scope_key = "inventory_dashboard_auto_flow_scope"
    if requested_flow:
        st.session_state[scope_key] = requested_flow
    active_flow = st.session_state.get(scope_key)
    selected_missing_dates = (
        _filter_automatic_missing_dates(
            automatic_missing_dates, active_flow
        )
        if active_flow else automatic_missing_dates
    )
    if active_flow and not selected_missing_dates:
        st.session_state.pop(scope_key, None)
        active_flow = None
        selected_missing_dates = automatic_missing_dates
    _render_automatic_daily_operation(
        supabase, selected_missing_dates,
        auto_load=bool(requested_flow),
        flow_scope=active_flow,
    )


def _render_completion_overview(
    summary, completed, today, start_date,
    history_end, check_days, missing,
):
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
    operation_table = build_daily_operation_table(
        summary, completed, today
    )
    requested_flow = _render_operation_table(operation_table)
    st.caption(
        "今日尚未结束，显示“进行中”属于正常进度，不计入待补日期。"
    )
    return requested_flow


def _render_operation_table(operation_table):
    widths = [1.25, 0.9, 0.8, 1.8, 0.8, 1.55, 0.85]
    headers = [
        "出库项目", "数据方式", "截止昨日", "待补日期",
        "今日状态", "当前操作", "补录入口",
    ]
    header_columns = st.columns(widths)
    for column, label in zip(header_columns, headers):
        column.markdown(f"**{label}**")

    requested_flow = None
    for row in operation_table.to_dict("records"):
        columns = st.columns(widths)
        values = [
            row["出库项目"], row["数据方式"], row["截止昨日"],
            row["待补日期"], row["今日状态"], row["当前操作"],
        ]
        for column, value in zip(columns[:6], values):
            column.write(value)
        project = row["出库项目"]
        needs_action = row["待补日期"] != "无"
        if not needs_action:
            columns[6].write("—")
        elif project == "黑白短袖":
            columns[6].page_link(
                "pages/4_库存.py", label="去补录"
            )
        elif project == "DTF 耗材":
            columns[6].page_link(
                "pages/9_耗材库存.py", label="去补录"
            )
        elif columns[6].button(
            "预览补录",
            key=f"inventory_dashboard_preview_{project}",
            width="stretch",
        ):
            requested_flow = project
    return requested_flow


def _filter_automatic_missing_dates(missing_dates, flow_label):
    return {
        movement_date: flow_label
        for movement_date, labels in missing_dates.items()
        if flow_label in str(labels)
    }


def _render_automatic_daily_operation(
    supabase, missing_dates, auto_load=False, flow_scope=None
):
    if not missing_dates:
        st.success("彩色短袖和 UV 在当前检查范围内均已完成扣减。")
        return
    labels = "、".join(str(value) for value in missing_dates.values())
    needs_colored = "彩色短袖" in labels
    needs_uv = "UV 生产库存" in labels
    st.markdown("#### 系统待补处理")
    if flow_scope:
        scope_columns = st.columns([3, 1])
        scope_columns[0].info(f"当前仅预览：{flow_scope}")
        if scope_columns[1].button(
            "查看全部",
            key="inventory_dashboard_show_all_auto_flows",
            width="stretch",
        ):
            st.session_state.pop(
                "inventory_dashboard_auto_flow_scope", None
            )
            st.rerun()
    source_descriptions = []
    if needs_colored:
        source_descriptions.append("彩色短袖生产数据")
    if needs_uv:
        source_descriptions.append("UV Google Sheets")
    st.caption("预览并补扣" + "和".join(source_descriptions) + "。")
    if needs_colored:
        st.info(
            f"彩色短袖快速补录平台：{COLORED_FAST_PLATFORM_SCOPE}。"
            "其他低量平台不阻塞本次补录，完整生产数据仍由生产数据页面核对。"
        )
    options = sorted(missing_dates)
    st.caption(
        "待补扣日期：" + "；".join(
            f"{value:%Y-%m-%d}（{missing_dates[value]}）"
            for value in options
        )
    )
    if needs_uv:
        spreadsheet = render_uv_spreadsheet_selector(
            key="inventory_dashboard_uv_spreadsheet"
        )
    else:
        spreadsheet = {"id": ""}
    state_key = "inventory_dashboard_auto_previews"
    identity_key = "inventory_dashboard_auto_preview_identity"
    identity = (
        tuple(
            (value.isoformat(), missing_dates[value])
            for value in options
        ),
        spreadsheet["id"],
    )
    load_requested = st.button(
        "一键读取全部待补日期",
        type="secondary",
        width="stretch",
        key="inventory_dashboard_auto_load",
    )
    if auto_load or load_requested:
        sheets_client = None
        if needs_uv:
            try:
                sheets_client = google_sheets_client()
            except Exception:
                sheets_client = None
        secrets = dict(st.secrets)
        progress_rows = {
            movement_date: {
                "日期": movement_date,
                "项目": missing_dates[movement_date],
                "进度": "等待处理",
            }
            for movement_date in options
        }
        progress_status = st.status(
            "正在按天处理补录数据...", expanded=True
        )
        progress_placeholder = progress_status.empty()

        def report_day_progress(movement_date, project, state):
            progress_rows[movement_date] = {
                "日期": movement_date,
                "项目": project,
                "进度": state,
            }
            progress_placeholder.dataframe(
                pd.DataFrame(progress_rows.values()).sort_values("日期"),
                hide_index=True,
                width="stretch",
                column_config={
                    "日期": st.column_config.DateColumn("日期"),
                    "项目": st.column_config.TextColumn("项目"),
                    "进度": st.column_config.TextColumn("进度"),
                },
            )

        with progress_status:
            previews = load_automatic_daily_batch_previews(
                supabase,
                missing_dates,
                sheets_client,
                spreadsheet["id"],
                ensure_colored_source=lambda movement_date: (
                    sync_production_day(
                        movement_date,
                        secrets=secrets,
                        required_platforms=COLORED_PRIMARY_PLATFORMS,
                    )
                ),
                max_day_workers=2,
                report_day_progress=report_day_progress,
            )
        has_errors = any(
            row["进度"] == "生产数据读取失败"
            for row in progress_rows.values()
        )
        progress_status.update(
            label=(
                "补录预览已生成，部分日期读取失败"
                if has_errors else "全部日期的补录预览已生成"
            ),
            state="error" if has_errors else "complete",
            expanded=has_errors,
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
            "数据范围": st.column_config.TextColumn(
                "数据范围", width="large"
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
            if preview.message:
                st.info(preview.message)
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
            st.dataframe(
                _system_stock_change_display(preview.rows),
                hide_index=True,
                width="stretch",
            )
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
        refreshed_completed = {}
        try:
            _summary, refreshed_completed, _start = (
                load_daily_completion_status(
                    supabase, datetime.now(NY_TIMEZONE).date()
                )
            )
        except Exception:
            refreshed_completed = {}
        details = "；".join(
            _format_applied_result(
                movement_date, code, labels[code], quantity,
                refreshed_completed,
            )
            for (movement_date, code), quantity in results.items()
        )
        st.session_state["inventory_dashboard_saved_message"] = (
            f"系统库存补扣完成，完成状态已重新核对：{details}"
        )
    if errors:
        st.session_state["inventory_dashboard_error_message"] = "；".join(
            f"{movement_date:%m/%d} {labels[code]}：{message}"
            for (movement_date, code), message in errors.items()
        )
    st.session_state.pop(state_key, None)
    st.session_state.pop(identity_key, None)
    st.rerun()


def _format_applied_result(
    movement_date, code, label, quantity, completed,
):
    is_completed = movement_date in set(completed.get(code, set()))
    status = "已完成" if is_completed else "仍有待处理数据"
    return (
        f"{movement_date:%m/%d} {label} {quantity:,} 件（{status}）"
    )


def _system_stock_change_display(rows):
    display = pd.DataFrame(rows).rename(columns={
        "预计扣减": "本次出库 (-)",
        "扣减后库存": "调整后库存",
    })
    if "本次出库 (-)" in display:
        display["本次出库 (-)"] = -pd.to_numeric(
            display["本次出库 (-)"], errors="coerce"
        ).fillna(0).abs().astype(int)
    return display
