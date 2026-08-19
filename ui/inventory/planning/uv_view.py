"""UV consumption and daily inventory-deduction views."""

from hashlib import sha1

import pandas as pd

import streamlit as st

from automation.sync.uv_daily_operation import (
    PHONE_CASE_PENDING_STATUS,
    PHONE_CASE_PRODUCT,
    apply_daily_sync,
    build_daily_deduction_scope,
    build_phone_case_allocation_preview,
    build_daily_sync_preview,
    phone_case_sku_key,
    phone_case_sku_label,
)
from automation.sync.uv_sheet_inventory import load_daily_summary
from db.inventory.core.queries import load_inventory_items
from db.inventory.planning.uv_consumption import (
    UV_CONSUMPTION_LOOKBACK_DAYS,
    UV_GOOGLE_DRIVE_FOLDER_URL,
    load_uv_consumption_history,
)
from ui.inventory.i18n import t
from ui.table_layout import fit_table_height
from ui.inventory.operations.system_deduction import system_deduction_comparison
from ui.operations import render_stock_change_review
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)
from utils.auth.session import get_current_operator_name, has_permission


def render_uv_consumption_model(
    supabase, category, current_date, visible_sizes=None,
):
    try:
        model = load_uv_consumption_history(supabase, current_date)
        if category:
            model = model[model["品类"] == category]
        if visible_sizes:
            model = model[model["型号"].isin(visible_sizes)]
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return
    st.subheader("UV 每日消耗模型")
    st.caption(
        f"每日消耗按 Google Sheets 最近 {UV_CONSUMPTION_LOOKBACK_DAYS} 天"
        "的有效数据日计算。点货、库存覆盖和全部在途货柜统一在“点货预测”计算；"
        "每日扣减在“系统库存扣减”。"
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
    if not category and model["品类"].eq("手机壳").any():
        production_tab, phone_tab = st.tabs(["UV 生产库存", "手机壳"])
        with production_tab:
            _render_uv_model_table(model[model["品类"] != "手机壳"])
        with phone_tab:
            st.caption("手机壳按刀模材质和机型独立展示，不与其他 UV SKU 混排。")
            _render_uv_model_table(model[model["品类"] == "手机壳"])
    else:
        _render_uv_model_table(model)


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
    ready_preview, pending, blocking = _render_preview(
        supabase, preview, current_date
    )
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
        _apply_preview(
            supabase, ready_preview, current_date, state_key, date_key
        )


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


def _render_preview(supabase, preview, current_date):
    st.caption(f"扣减日期：{current_date:%Y-%m-%d}")
    production = preview[preview["表格产品"] != PHONE_CASE_PRODUCT].copy()
    phone = preview[preview["表格产品"] == PHONE_CASE_PRODUCT].copy()
    production_tab, phone_tab = st.tabs(["UV 生产库存", "手机壳"])
    with production_tab:
        render_stock_change_review(
            system_deduction_comparison(production),
            action="出库",
            title="UV 生产库存每日扣减核对",
            identity_columns=[
                "状态", "表格产品", "品类", "材质", "颜色", "型号",
            ],
            extra_columns=["当日消耗"],
            unit="件",
            quantity_format="%d",
        )
    with phone_tab:
        phone_allocations, phone_blocking = _render_phone_case_allocation(
            supabase, phone, current_date
        )
    ready, pending, blocking = build_daily_deduction_scope(
        preview,
        phone_allocations,
        phone_case_complete=not phone_blocking,
    )
    if phone_blocking:
        st.info("Iphone 使用独立手机壳扣减流程，本次不会影响其他 UV SKU。")
    st.caption(
        f"本次预计扣减：{int(pending['预计扣减'].sum()):,} 件｜"
        f"已同步：{int((preview['状态'] == '已同步').sum())} 个 SKU"
    )
    return ready, pending, blocking


def _render_phone_case_allocation(supabase, phone_summary, current_date):
    if phone_summary.empty:
        st.info("今日 Google Sheets 没有手机壳消耗。")
        return phone_summary, ""
    summary = phone_summary.iloc[0]
    if summary["状态"] == "已同步":
        st.success(f"今日手机壳 {int(summary['当日消耗']):,} 件已经扣减。")
        return phone_summary.iloc[0:0].copy(), ""
    if summary["状态"] != PHONE_CASE_PENDING_STATUS:
        st.error(str(summary["状态"]))
        return phone_summary, str(summary["状态"])

    required = int(summary["当日消耗"])
    inventory = load_inventory_items(supabase, "UV", "手机壳")
    inventory = inventory[
        inventory["material"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    inventory["_sku_key"] = inventory.apply(
        lambda row: phone_case_sku_key(row.to_dict()), axis=1
    )
    labels = {
        row["_sku_key"]: phone_case_sku_label(row)
        for row in inventory.to_dict("records")
    }
    selected = st.multiselect(
        "选择今天实际消耗的手机壳材质与型号",
        options=inventory["_sku_key"].tolist(),
        format_func=lambda key: labels.get(key, key),
        key=f"uv_phone_case_skus_{current_date:%Y%m%d}",
        placeholder="可搜索材质或 iPhone 型号",
    )
    selected_inventory = inventory[inventory["_sku_key"].isin(selected)]
    editor = selected_inventory[[
        "_sku_key", "material", "size", "quantity",
    ]].rename(columns={
        "material": "材质", "size": "型号", "quantity": "当前库存",
    })
    editor["本次出库"] = 0
    signature = sha1("|".join(selected).encode()).hexdigest()[:10]
    edited = pd.DataFrame(st.data_editor(
        editor,
        hide_index=True,
        width="stretch",
        disabled=["_sku_key", "材质", "型号", "当前库存"],
        column_config={
            "_sku_key": None,
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "本次出库": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"
            ),
        },
        key=f"uv_phone_case_allocation_{current_date:%Y%m%d}_{signature}",
    ))
    allocations = {
        str(row["_sku_key"]): int(row["本次出库"] or 0)
        for row in edited.to_dict("records")
    }
    allocation_rows = build_phone_case_allocation_preview(
        inventory, allocations
    )
    allocated = int(allocation_rows.get(
        "预计扣减", pd.Series(dtype=float)
    ).sum())
    st.metric("Google Sheets 手机壳总消耗", f"{required:,} 件")
    st.metric("已分配到具体型号", f"{allocated:,} 件")
    if not allocation_rows.empty:
        render_stock_change_review(
            system_deduction_comparison(allocation_rows),
            action="出库",
            title="手机壳型号扣减核对",
            identity_columns=["状态", "材质", "型号"],
            extra_columns=["当日消耗"],
            unit="件",
            quantity_format="%d",
        )
    if allocated != required:
        difference = required - allocated
        message = (
            f"还需分配 {difference:,} 件"
            if difference > 0 else f"已超出表格总数 {abs(difference):,} 件"
        )
        st.warning(message)
        return allocation_rows, message
    if (allocation_rows["状态"] == "库存不足").any():
        return allocation_rows, "存在库存不足的手机壳型号"
    return allocation_rows, ""


def _render_deferred(preview):
    deferred = preview[preview["状态"] == "待分配 SKU（本次不扣）"]
    if not deferred.empty:
        details = "；".join(
            f"{row['表格产品']} {int(row['当日消耗'])} 件"
            for row in deferred.to_dict("records")
        )
        st.warning(f"{details} 缺少具体 SKU，本次不会扣减。")


def _render_uv_model_table(model):
    if model.empty:
        st.info("当前分类暂无已同步消耗数据。")
        return
    st.dataframe(
        model, hide_index=True, width="stretch",
        height=fit_table_height(model),
        column_config={
            "每日消耗": st.column_config.NumberColumn(format="%.1f"),
            "自然日均消耗": st.column_config.NumberColumn(format="%.1f"),
            "窗口总消耗": st.column_config.NumberColumn(format="%.0f"),
        },
    )


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
