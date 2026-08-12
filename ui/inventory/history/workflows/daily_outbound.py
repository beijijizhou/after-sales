"""Auditable daily-outbound correction workflow."""

import pandas as pd
import streamlit as st

from db.inventory import normalize_adjustment_rows
from db.inventory.operations.daily_outbound_versions import (
    build_daily_outbound_edit_rows as build_versioned_outbound_edit_rows,
    load_daily_outbound_revision_by_inventory_batch,
    save_daily_outbound_revision,
)
from db.inventory.operations.outbound_audit import (
    DAILY_OUTBOUND_REASONS,
    audit_outbound_batch,
    build_daily_outbound_edit_rows,
    build_replacement_inventory,
    find_outbound_inventory_issues,
    load_daily_outbound_batch,
    load_outbound_inventory,
    replace_daily_outbound_batch,
)
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_adjustment_preview_editor,
    render_inventory_change_comparison,
)
from utils.auth import get_current_operator_name


def is_editable_daily_outbound(selected_df):
    if selected_df.empty:
        return False
    reasons = selected_df["reason"].fillna("").astype(str)
    quantities = pd.to_numeric(
        selected_df["quantity_change"], errors="coerce"
    ).fillna(0)
    return reasons.isin(DAILY_OUTBOUND_REASONS).all() and quantities.lt(0).all()


def render_daily_outbound_replacement(supabase, batch_id):
    st.markdown("#### 修改每日出库记录")
    st.caption(
        "保存时会自动撤销原批次并生成修正版批次；原记录和撤销记录都会保留。"
        "编辑器读取该批次的全部 SKU，不受上方筛选条件影响。"
    )
    complete = _load_editable_batch(supabase, batch_id)
    if complete is None:
        return
    versioned = _load_versioned_revision(supabase, batch_id)
    original = (
        build_versioned_outbound_edit_rows(versioned)
        if versioned else build_daily_outbound_edit_rows(complete)
    )
    edited = render_adjustment_preview_editor(
        original, key=f"daily_outbound_replacement_{batch_id}",
        lock_operation=True, lock_identity=False, allow_rows=True,
        disabled_columns=["备注"],
    )
    corrected = normalize_adjustment_rows(edited)
    movement_date = _validate_correction(original, corrected)
    if movement_date is None:
        return
    corrected["备注"] = "仓库每日出货"
    original_total = int(original["数量"].sum())
    corrected_total = int(corrected["数量"].sum())
    _render_totals(original_total, corrected_total)
    row = complete.iloc[0]
    try:
        current = load_outbound_inventory(
            supabase, row["department"], row["category"]
        )
        replacement = build_replacement_inventory(current, complete)
        issues = find_outbound_inventory_issues(corrected, replacement)
    except Exception as error:
        st.error(f"修正版库存检查失败：{error}")
        return
    changes = pd.concat([
        movement_rows_as_adjustments(complete, reverse=True),
        corrected.assign(部门=row["department"], 品类=row["category"]),
    ], ignore_index=True)
    render_inventory_change_comparison(
        build_inventory_change_comparison(current.assign(
            department=row["department"], category=row["category"]
        ), changes), title="修正后库存核对",
    )
    if not issues.empty:
        st.warning(
            "修正版存在库存不足：申报数量会完整保存，库存只扣到 0，"
            "缺口进入版本记录；不会生成临时入库。"
        )
        st.dataframe(issues, hide_index=True, width="stretch")
    if not _confirmed(batch_id):
        return
    _save_correction(
        supabase, batch_id, complete, corrected, versioned, movement_date,
        original_total, corrected_total,
    )


def movement_rows_as_adjustments(rows, reverse=False):
    result = pd.DataFrame(rows).rename(columns={
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码",
    }).copy()
    quantity = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0).astype(int)
    if reverse:
        quantity = -quantity
    result["操作"] = quantity.map(lambda value: "增加" if value > 0 else "扣减")
    result["数量"] = quantity.abs()
    return result[["部门", "品类", "品牌", "材质", "颜色", "尺码", "操作", "数量"]]


def _load_editable_batch(supabase, batch_id):
    try:
        batch = load_daily_outbound_batch(supabase, batch_id)
    except Exception as error:
        st.error(f"读取完整出库批次失败：{error}")
        return None
    if batch.empty:
        st.error("没有找到这笔出库批次，可能已被其他用户处理。")
        return None
    if not is_editable_daily_outbound(batch):
        st.error("完整批次不是可修改的每日出库记录，请刷新后重试。")
        return None
    return batch


def _load_versioned_revision(supabase, batch_id):
    try:
        return load_daily_outbound_revision_by_inventory_batch(supabase, batch_id)
    except Exception:
        return None


def _validate_correction(original, corrected):
    if corrected.empty:
        st.warning("修正版不能为空；如果要删除整笔记录，请选择“仅撤销”。")
        return None
    dates = pd.to_datetime(original["日期"], errors="coerce").dt.date.dropna().unique()
    if len(dates) != 1:
        st.error("这笔批次包含多个出库日期，暂时不能修改。")
        return None
    if not corrected["日期"].eq(dates[0]).all():
        st.error(f"出库日期必须保持为 {dates[0]}。")
        return None
    return dates[0]


def _render_totals(original, corrected):
    columns = st.columns(3)
    columns[0].metric("原出库", f"{original:,} 件")
    columns[1].metric("修正后", f"{corrected:,} 件")
    columns[2].metric("变化", f"{corrected - original:+,} 件")


def _confirmed(batch_id):
    confirmed = st.checkbox(
        "我已核对修正版，并确认撤销原批次后生成新批次",
        key=f"confirm_daily_outbound_replacement_{batch_id}",
    )
    return st.button(
        "保存修正版", type="primary", width="stretch", disabled=not confirmed,
        key=f"save_daily_outbound_replacement_{batch_id}",
    )


def _save_correction(supabase, batch_id, complete, corrected, versioned,
                     movement_date, original_total, corrected_total):
    row = complete.iloc[0]
    try:
        if versioned:
            save_daily_outbound_revision(
                supabase, row["department"], row["category"], movement_date,
                corrected, get_current_operator_name(),
                daily_outbound_batch_id=versioned["daily_outbound_batch_id"],
                note=f"修改每日出库：{original_total} → {corrected_total}",
            )
            passed, mismatches = True, pd.DataFrame()
        else:
            replacement_id = replace_daily_outbound_batch(
                supabase, batch_id, row["department"], row["category"],
                complete, corrected, get_current_operator_name(),
            )
            audit, mismatches = audit_outbound_batch(
                supabase, replacement_id, corrected
            )
            passed = audit["passed"]
    except Exception as error:
        st.error(f"修改每日出库失败：{error}")
        return
    if not passed:
        st.error("修正版已写入，但自动核验未通过，请立即查看差异。")
        st.dataframe(mismatches, hide_index=True, width="stretch")
        return
    st.session_state["inventory_saved_message"] = (
        f"每日出库已修改：{original_total:,} → {corrected_total:,} 件"
    )
    st.rerun()
