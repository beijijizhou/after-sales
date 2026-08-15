"""ERP and pasted-data synchronization views for logistics review."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date
from queue import Empty, Queue
import threading

import pandas as pd
import streamlit as st

from automation.logistics import parse_logistics_frame
from automation.logistics.stages import STAGE_CODES, STAGE_OPTIONS
from automation.api.humbird import HUMBIRD_OPEN_LOGISTICS_PLATFORMS
from automation.production import (
    PLATFORMS_BY_DEPARTMENT,
    PRODUCTION_DEPARTMENTS,
    SDS_PLATFORM_PROFILES,
)
from db.logistics import backfill_tracking_check_sources, upsert_shipments
from ui.logistics.review.model import (
    classify_carrier_rows,
    default_logistics_platforms,
    is_target_usps_review,
    label_ocr_candidates,
    order_tracking_pairs,
)
from ui.logistics.review.state import reset_review_selection
from ui.logistics.review.view import render_carrier_review
from ui.logistics.source_gateway import (
    fetch_source,
    render_s2b_connection_status,
)
from utils.auth import has_permission


CONNECTED_PLATFORMS = {
    *HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    "S2B", "七创", "一朵云", *SDS_PLATFORM_PROFILES,
}
ORDER_STAGES = STAGE_CODES


def render_sync(supabase):
    auto_tab, upload_tab = st.tabs(["从ERP自动读取", "复制粘贴订单物流"])
    with auto_tab:
        _render_erp_sync(supabase)
    with upload_tab:
        _render_upload_sync(supabase)
    st.divider()
    render_carrier_review(supabase, True)


def _render_erp_sync(supabase):
    st.subheader("从ERP读取订单与物流单号")
    columns = st.columns(2)
    department = columns[0].selectbox(
        "部门", PRODUCTION_DEPARTMENTS, key="logistics_department"
    )
    platforms = tuple(PLATFORMS_BY_DEPARTMENT.get(department, ()))
    connected = [item for item in platforms if item in CONNECTED_PLATFORMS]
    pending = [item for item in platforms if item not in CONNECTED_PLATFORMS]
    selected = columns[1].multiselect(
        "生产平台（仅显示已接入物流接口）", connected,
        default=default_logistics_platforms(platforms, CONNECTED_PLATFORMS),
        key=f"logistics_platforms_{department}",
    )
    st.caption(
        f"{department} 已配置平台：{'、'.join(platforms) or '暂无'}｜"
        f"已接入物流接口：{'、'.join(connected) or '暂无'}｜"
        f"尚未接入物流接口：{'、'.join(pending) or '无'}"
    )
    stage = st.selectbox("订单阶段", STAGE_OPTIONS)
    st.caption(
        "未接单＝尚未形成批次｜已接单（生产中）＝批次已生成｜"
        "已发货＝生产完成并通过质检（ERP也可能显示“已生产”）"
    )
    dates = st.columns(2)
    start_date = dates[0].date_input(
        "开始日期", value=date.today()
    )
    end_date = dates[1].date_input("结束日期", value=date.today())
    st.caption("默认仅读取当天数据；需要历史核查时再手动扩大日期范围。")
    render_s2b_connection_status(selected)
    if set(selected) & HUMBIRD_OPEN_LOGISTICS_PLATFORMS:
        st.caption(
            "蜂鸟授权顺序：官方开放API → 数据库共享Token直连 → "
            "仅在前两级不可用时由管理员本地登录并自动更新数据库Token。"
        )
    if not st.button(
        "从ERP读取数据", type="primary", disabled=not selected,
        width="stretch",
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有同步物流数据的权限。")
        return
    _load_selected_sources(
        supabase, selected, department, stage, start_date, end_date
    )


def _load_selected_sources(
    supabase, selected, department, stage, start_date, end_date,
):
    all_rows, errors, reviewed_rows = [], [], []
    total = len(selected)
    progress = st.progress(0)
    status = st.status(
        f"正在准备读取 {total:,} 个ERP平台...", expanded=True
    )
    platform_states = {
        source: {
            "平台": source,
            "最新状态": "等待开始",
            "读取": None,
            "普通USPS": None,
            "面单": None,
            "已过滤": None,
        }
        for source in selected
    }
    state_table = st.empty()
    _render_platform_states(state_table, platform_states)
    fetched = _fetch_selected_sources(
        selected, department, ORDER_STAGES[stage], start_date, end_date,
        status, progress, state_table, platform_states,
    )
    for index, source in enumerate(selected, start=1):
        status.update(
            label=f"{source}：正在处理读取结果（{index}/{total}）",
            state="running", expanded=True,
        )
        try:
            result = fetched[source]
            if isinstance(result, Exception):
                raise result
            rows = result
            _update_platform_state(
                state_table, platform_states, source,
                f"已获取 {len(rows):,} 条，正在保存",
                读取=len(rows),
            )
            for row in rows:
                row.update({
                    "local_acceptance_status": stage,
                    "department": department,
                })
            saved_shipments = pd.DataFrame(upsert_shipments(supabase, rows))
            backfill_tracking_check_sources(supabase, saved_shipments)
            _update_platform_state(
                state_table, platform_states, source,
                "数据已保存，正在识别物流商",
            )
            reviewed = classify_carrier_rows(rows)
            reviewed_rows.extend(reviewed)
            usps_rows = [
                item["row"] for item in reviewed
                if is_target_usps_review(item)
            ]
            all_rows.extend(usps_rows)
            label_count = len(label_ocr_candidates(reviewed))
            _update_platform_state(
                state_table, platform_states, source, "处理完成",
                读取=len(rows),
                普通USPS=len(usps_rows),
                面单=label_count,
                已过滤=len(rows) - len(usps_rows),
            )
        except Exception as error:
            errors.append(f"{source}：{error}")
            _update_platform_state(
                state_table, platform_states, source,
                f"读取失败：{error}",
            )
    st.session_state["logistics_usps_candidates"] = order_tracking_pairs(all_rows)
    st.session_state["logistics_carrier_review_rows"] = reviewed_rows
    reset_review_selection()
    if all_rows:
        st.success(
            f"本次读取到 {len(all_rows):,} 条普通 USPS；"
            "订单、物流单号、平台账号和面单链接已保存。"
        )
    if errors:
        st.warning("；".join(errors))
        status.update(
            label=f"ERP读取完成，但有 {len(errors):,} 个平台失败",
            state="error", expanded=True,
        )
    else:
        status.update(
            label=(
                f"ERP读取完成：已准备 {len(all_rows):,} 条普通USPS待核查数据"
            ),
            state="complete", expanded=False,
        )


def _fetch_selected_sources(
    selected,
    department,
    stage,
    start_date,
    end_date,
    status,
    progress,
    state_table=None,
    platform_states=None,
):
    platform_states = platform_states or {
        source: {"平台": source, "最新状态": "等待开始"}
        for source in selected
    }
    if len(selected) == 1:
        source = selected[0]
        status.update(
            label=f"{source}：正在连接ERP（1/1）",
            state="running", expanded=True,
        )
        _update_platform_state(
            state_table, platform_states, source,
            "正在请求订单和面单数据",
        )
        try:
            rows = fetch_source(
                source, department, stage, start_date, end_date,
                report_progress=lambda message: _update_platform_state(
                    state_table, platform_states, source, message,
                ),
            )
            progress.progress(1.0)
            return {source: rows}
        except Exception as error:
            progress.progress(1.0)
            return {source: error}

    status.update(
        label=f"正在并行读取 {len(selected):,} 个ERP平台（最多4线程）",
        state="running", expanded=True,
    )
    messages = Queue()
    script_context = _script_context()

    def worker(source):
        _attach_script_context(script_context)
        return fetch_source(
            source, department, stage, start_date, end_date,
            report_progress=lambda message: messages.put((source, message)),
        )

    results = {}
    for source in selected:
        _update_platform_state(
            state_table, platform_states, source, "正在连接ERP",
        )
    with ThreadPoolExecutor(max_workers=min(4, len(selected))) as pool:
        pending = {pool.submit(worker, source): source for source in selected}
        while pending:
            completed, _ = wait(
                pending, timeout=0.25, return_when=FIRST_COMPLETED
            )
            _drain_progress_messages(
                messages, state_table, platform_states
            )
            for future in completed:
                source = pending.pop(future)
                try:
                    results[source] = future.result()
                    message = (
                        f"获取完成：{len(results[source]):,} 条，等待保存"
                    )
                except Exception as error:
                    results[source] = error
                    message = f"读取失败：{error}"
                _update_platform_state(
                    state_table, platform_states, source, message,
                )
                progress.progress(len(results) / len(selected))
        _drain_progress_messages(messages, state_table, platform_states)
    return results


def _drain_progress_messages(messages, state_table, platform_states):
    while True:
        try:
            source, message = messages.get_nowait()
        except Empty:
            return
        _update_platform_state(
            state_table, platform_states, source, message,
        )


def _update_platform_state(
    state_table, platform_states, source, message, **metrics,
):
    platform_states[source]["最新状态"] = str(message)
    platform_states[source].update(metrics)
    _render_platform_states(state_table, platform_states)


def _render_platform_states(state_table, platform_states):
    if state_table is None:
        return
    frame = pd.DataFrame(platform_states.values())
    state_table.dataframe(
        frame, hide_index=True, width="stretch",
        column_config={
            "平台": st.column_config.TextColumn("平台"),
            "最新状态": st.column_config.TextColumn("最新状态", width="large"),
            "读取": st.column_config.NumberColumn("读取", format="%d"),
            "普通USPS": st.column_config.NumberColumn(
                "普通USPS", format="%d"
            ),
            "面单": st.column_config.NumberColumn("面单", format="%d"),
            "已过滤": st.column_config.NumberColumn("已过滤", format="%d"),
        },
    )


def _script_context():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx()
    except ImportError:
        return None


def _attach_script_context(context):
    if context is None:
        return
    from streamlit.runtime.scriptrunner import add_script_run_ctx
    add_script_run_ctx(threading.current_thread(), context)


def _render_upload_sync(supabase):
    st.subheader("复制粘贴订单与物流单号")
    st.caption(
        "在Excel里复制两列，点击下方第一格后直接粘贴；"
        "第一列订单号，第二列物流单号。"
    )
    scope = st.columns(3)
    department = scope[0].selectbox(
        "部门", PRODUCTION_DEPARTMENTS,
        key="logistics_manual_department",
    )
    platform = scope[1].text_input(
        "平台", value="手工输入", key="logistics_manual_platform"
    )
    account = scope[2].text_input(
        "ERP账号", value="manual", key="logistics_manual_account"
    )
    entry = st.data_editor(
        pd.DataFrame([{"订单号": "", "物流单号": ""}]),
        hide_index=True, num_rows="dynamic", width="stretch",
        column_config={
            "订单号": st.column_config.TextColumn("订单号", required=False),
            "物流单号": st.column_config.TextColumn("物流单号", required=False),
        }, key="logistics_order_tracking_paste",
    )
    rows, issues = parse_logistics_frame(entry, defaults={
        "department": department,
        "erp_platform": platform.strip() or "手工输入",
        "erp_account": account.strip() or "manual",
    })
    if not rows and not issues:
        st.info("填写后会先校验并进入“物流识别核对”，不会直接查询USPS。")
    if issues:
        st.error("导入已停止：" + "；".join(issues[:20]))
        if len(issues) > 20:
            st.caption(f"另有 {len(issues) - 20:,} 行错误未显示。")
        return
    st.caption(f"校验通过：{len(rows):,} 条订单物流记录。")
    if not st.button(
        "进行物流识别", type="primary", width="stretch", disabled=not rows,
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有导入物流数据的权限。")
        return
    try:
        saved_shipments = pd.DataFrame(upsert_shipments(supabase, rows))
        backfill_tracking_check_sources(supabase, saved_shipments)
    except Exception as error:
        st.error(database_error(error))
        return
    reviewed = classify_carrier_rows(rows)
    st.session_state["logistics_carrier_review_rows"] = reviewed
    st.session_state["logistics_usps_candidates"] = order_tracking_pairs([
        item["row"] for item in reviewed if is_target_usps_review(item)
    ])
    reset_review_selection()
    usps_count = sum(is_target_usps_review(item) for item in reviewed)
    st.success(
        f"已保存 {len(rows):,} 条｜普通USPS {usps_count:,} 条｜"
        f"其他物流 {len(rows) - usps_count:,} 条"
    )
