"""UV consumption and daily inventory-deduction views."""

import streamlit as st

from automation.sync.uv_daily_operation import (
    SYNCABLE_STATUSES,
    apply_daily_sync,
    build_daily_sync_preview,
)
from automation.sync.uv_sheet_inventory import load_daily_summary
from db.inventory.container.repository import load_inventory_containers
from db.inventory.core.queries import load_inventory_items
from db.inventory.planning.uv_consumption import (
    UV_CONSUMPTION_LOOKBACK_DAYS,
    UV_GOOGLE_DRIVE_FOLDER_URL,
    build_uv_container_coverage,
    load_uv_consumption_history,
)
from ui.inventory.i18n import t
from ui.inventory.operations.system_deduction import system_deduction_display
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)
from utils.auth.session import get_current_operator_name, has_permission


def render_uv_consumption_model(
    supabase, category, current_date, visible_sizes=None, inventory_df=None,
):
    try:
        model = load_uv_consumption_history(supabase, current_date)
        if category:
            model = model[model["品类"] == category]
        if visible_sizes:
            model = model[model["型号"].isin(visible_sizes)]
        containers = load_inventory_containers(
            supabase, department="UV", category=category or None,
            statuses=["在途", "未到货", "延迟", "已到柜", "已到货"],
        )
        coverage = build_uv_container_coverage(model, inventory_df, containers)
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    st.subheader("UV 每日消耗与货柜")
    st.caption(
        f"每日消耗按 Google Sheets 最近 {UV_CONSUMPTION_LOOKBACK_DAYS} 天"
        "的有效数据日计算，并连接当前库存和货柜。每日扣减在“系统库存扣减”。"
    )
    if model.empty:
        st.info("最近 14 天暂无已同步的 UV 每日消耗数据")
        return
    daily_total = float(model["每日消耗"].sum())
    effective_days = int(model["有效数据天数"].max())
    columns = st.columns(2)
    columns[0].metric("一天消耗", f"{daily_total:,.1f} 件")
    columns[1].metric("计算所用有效天数", f"{effective_days} 天")
    if effective_days < UV_CONSUMPTION_LOOKBACK_DAYS:
        st.warning(f"最近 14 天中只有 {effective_days} 天已同步。")
    st.dataframe(
        coverage, hide_index=True, width="stretch",
        column_config={
            "每日消耗": st.column_config.NumberColumn(format="%.1f"),
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "当前可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
            "预计到货日期": st.column_config.DateColumn(),
            "货柜数量": st.column_config.NumberColumn(format="%d"),
            "到货后可撑天数": st.column_config.NumberColumn(format="%.1f 天"),
        },
    )


def render_uv_daily_deduction(supabase, current_date):
    st.subheader("UV 系统库存扣减")
    st.caption("先读取今天的 Google Sheets 数据并核对；确认后才会扣减库存。")
    spreadsheet = render_uv_spreadsheet_selector()
    st.link_button("打开当前 Google 表格", spreadsheet["webViewLink"])
    st.link_button("打开 UV 数据文件夹", UV_GOOGLE_DRIVE_FOLDER_URL)
    result = st.session_state.pop("uv_daily_deduction_result", None)
    if result:
        st.success(result)
    state_key, date_key = "uv_daily_deduction_preview", "uv_daily_deduction_date"
    if st.button("读取今日消耗并生成表格", key="uv_load_daily_deduction"):
        _load_preview(
            supabase, spreadsheet["id"], current_date, state_key, date_key
        )
    preview = st.session_state.get(state_key)
    if preview is None or st.session_state.get(date_key) != current_date:
        return
    pending, blocking = _render_preview(preview, current_date)
    if not blocking.empty:
        details = "；".join(
            f"{row['表格产品']}：{row['状态']}"
            for row in blocking.to_dict("records")
        )
        st.error(f"暂不能扣减，请先处理：{details}")
        return
    _render_deferred(preview)
    if pending.empty:
        st.success("今天的消耗已经全部同步，无需再次扣减。")
        return
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能确认扣减库存。")
        return
    confirmed = st.checkbox(
        "我已核对以上 SKU、当日消耗和扣减后库存",
        key="uv_confirm_daily_deduction",
    )
    if st.button(
        "确认扣减今日库存", key="uv_apply_daily_deduction",
        type="primary", disabled=not confirmed,
    ):
        _apply_preview(supabase, preview, current_date, state_key, date_key)


def _load_preview(supabase, spreadsheet_id, current_date, state_key, date_key):
    try:
        summary = load_daily_summary(
            google_sheets_client(), spreadsheet_id, current_date
        )
        if not summary:
            st.session_state.pop(state_key, None)
            st.session_state.pop(date_key, None)
            st.warning(f"{current_date:%m/%d} 暂无可扣减的 SKU 消耗数据。")
            return
        inventory = load_inventory_items(supabase, "UV", "")
        st.session_state[state_key] = build_daily_sync_preview(
            supabase, summary, current_date, inventory
        )
        st.session_state[date_key] = current_date
    except Exception as error:
        st.error(f"读取今日消耗失败：{error}")


def _render_preview(preview, current_date):
    st.caption(f"扣减日期：{current_date:%Y-%m-%d}")
    display = system_deduction_display(preview)
    st.dataframe(display, hide_index=True, width="stretch")
    pending = preview[preview["状态"] == "可扣减"]
    blocking = preview[~preview["状态"].isin(SYNCABLE_STATUSES)]
    st.caption(
        f"本次预计扣减：{int(pending['预计扣减'].sum()):,} 件｜"
        f"已同步：{int((preview['状态'] == '已同步').sum())} 个 SKU"
    )
    return pending, blocking


def _render_deferred(preview):
    deferred = preview[preview["状态"] == "待分配 SKU（本次不扣）"]
    if not deferred.empty:
        details = "；".join(
            f"{row['表格产品']} {int(row['当日消耗'])} 件"
            for row in deferred.to_dict("records")
        )
        st.warning(f"{details} 缺少具体 SKU，本次不会扣减。")


def _apply_preview(supabase, preview, current_date, state_key, date_key):
    try:
        imported, skipped = apply_daily_sync(
            supabase, preview, current_date, get_current_operator_name()
        )
        st.session_state.pop(state_key, None)
        st.session_state.pop(date_key, None)
        st.session_state["uv_daily_deduction_result"] = (
            f"今日库存已扣减 {imported:,} 件"
            + (f"，另有 {skipped:,} 件此前已同步" if skipped else "")
        )
        st.rerun()
    except Exception as error:
        st.error(f"扣减失败：{error}")
