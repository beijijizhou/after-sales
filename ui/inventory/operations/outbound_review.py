"""Inventory review and commit step for daily outbound batches."""

import streamlit as st

from db.inventory import normalize_adjustment_rows
from db.inventory.operations.daily_outbound_versions import save_daily_outbound_revision
from db.inventory.operations.outbound_audit import find_outbound_inventory_issues, load_outbound_inventory
from ui.inventory.operations.adjustment_preview import build_inventory_change_comparison, render_inventory_change_comparison
from ui.inventory.operations.outbound_feedback import render_outbound_preview_summary
from utils.auth import get_current_operator_name


def render_outbound_review(
    supabase, department, category, movement_date, adjustments,
    package_preview, entry_text, text,
):
    """Render the mandatory inventory review and return saved total, or None."""
    st.markdown(f"#### {text['preview']}")
    _render_package_preview(package_preview, entry_text)
    adjustments = normalize_adjustment_rows(adjustments)
    if adjustments.empty:
        st.warning(text["empty"])
        return None
    total = render_outbound_preview_summary(adjustments, text)
    try:
        inventory = load_outbound_inventory(supabase, department, category)
        issues = find_outbound_inventory_issues(adjustments, inventory)
    except Exception as error:
        st.error(f"{text['inventory_check_error']}: {error}")
        return None
    render_inventory_change_comparison(
        build_inventory_change_comparison(inventory, adjustments), action="扣减"
    )
    _render_inventory_issues(issues, text)
    st.warning(text["unsaved"])
    if not st.button(text["confirm"], width="stretch", type="primary"):
        return None
    try:
        saved = save_daily_outbound_revision(
            supabase, department, category, movement_date, adjustments,
            get_current_operator_name(), note="仓库每日出货",
        )
    except Exception as error:
        st.error(f"{text['save_error']}: {error}")
        return None
    shortage = int(saved.get("shortage_total") or 0)
    if shortage:
        st.warning(
            f"仓库申报 {int(saved.get('requested_total') or total):,} 件已保存；"
            f"实际库存扣减 {int(saved.get('applied_total') or 0):,} 件；"
            f"未扣差额 {shortage:,} 件已进入批次核对。"
        )
    return total


def _render_package_preview(preview, text):
    if preview.empty:
        return
    display = preview.copy()
    display["包装单位"] = display["包装单位"].map(text["packages"])
    display = display.rename(columns={
        "品牌": text["brand"], "材质": text["material"], "颜色": text["color"],
        "尺码": text["size"], "包装单位": text["package"], "箱规": text["units"],
        "包装数量": text["count"], "总件数": text["total"],
    })
    st.dataframe(display, hide_index=True, width="stretch")


def _render_inventory_issues(issues, text):
    if issues.empty:
        return
    st.warning("当前出库存在库存不足。系统会完整保存仓库申报数量，库存只扣到 0，并单独记录未扣差额；不会生成临时入库。")
    st.dataframe(issues, hide_index=True, width="stretch", column_config={
        "数量": st.column_config.NumberColumn(text["outbound_quantity"], format="%d"),
        "当前库存": st.column_config.NumberColumn(text["current_inventory"], format="%d"),
        "缺口": st.column_config.NumberColumn(text["shortage"], format="%d"),
    })
    missing = int((issues["问题"] == "SKU 不存在").sum())
    if missing:
        st.warning(f"其中 {missing} 个 SKU 不存在：申报数据会保留，但该 SKU 本次实际库存扣减为 0。")
