from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory.operations.outbound_audit import (
    find_outbound_inventory_issues,
    load_outbound_inventory,
)
from db.inventory.sales import (
    allocate_brand_merged_sales,
    build_invoice_number,
    build_sales_adjustments,
    load_company_profile,
    load_customers,
    load_sales_invoices,
    normalize_sales_lines,
)
from ui.inventory.sales.customer_section import render_sales_parties
from ui.inventory.sales.history import render_invoice_history
from ui.inventory.sales.invoice_review import render_invoice_review
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from ui.inventory.shared.linked_sku_table import (
    render_linked_sku_sales_table,
)
from utils.sku_sorting import sort_sku_rows


def render_customer_sales_outbound(
    supabase, department, category, raw_df, can_edit, show_heading=True,
):
    if show_heading:
        st.subheader("客户销售出库与 Invoice")
        st.caption(
            "销售给公司或个人客户；保存后扣减库存、保留销售批次并生成 Invoice。"
        )
    if not can_edit:
        st.info("当前账号只有库存查看权限，不能创建销售出库。")
        return
    try:
        company = load_company_profile(supabase)
        customers = load_customers(supabase)
        invoices = load_sales_invoices(supabase)
    except Exception:
        st.error(
            "客户销售出库数据库尚未初始化，请先部署 "
            "sql/inventory/sales/01_customer_sales_invoices.sql。"
        )
        return

    entry_tab, history_tab = st.tabs(["新建销售出库", "Invoice 记录"])
    with entry_tab:
        _render_sales_entry(
            supabase, department, category, raw_df, company, customers
        )
    with history_tab:
        render_invoice_history(supabase, invoices, can_edit)


def _render_sales_entry(
    supabase, department, category, raw_df, company, customers,
):
    version = int(st.session_state.get("sales_invoice_version", 0))
    edited_company, edited_customer = render_sales_parties(
        supabase, company, customers, version
    )

    st.markdown("#### Invoice 与销售明细")
    left, right = st.columns(2)
    invoice_date = left.date_input(
        "Invoice 日期",
        value=datetime.now(ZoneInfo("America/New_York")).date(),
        key=f"sales_invoice_date_{version}",
    )
    invoice_number = right.text_input(
        "Invoice 编号",
        value=build_invoice_number(),
        key=f"sales_invoice_number_{version}",
    )
    note = st.text_input("Invoice 备注（可选）", key=f"sales_note_{version}")
    combine_brands = False
    if category == "彩色短袖":
        brand_rule = st.segmented_control(
            "彩色短袖品牌处理规则",
            ["跨品牌合并", "按品牌出库"],
            default="跨品牌合并",
            key="sales_colored_brand_rule",
        )
        combine_brands = brand_rule == "跨品牌合并"
        if combine_brands:
            st.caption(
                "同一材质、颜色和尺码合并销售；确认后按实际库存自动分摊到各品牌。"
            )
        else:
            st.caption("每一行选择具体品牌，并从该品牌库存中扣减。")
    edited_lines = render_linked_sku_sales_table(
        raw_df, f"sales_lines_{version}", combine_brands=combine_brands,
    )
    lines = sort_sku_rows(
        normalize_sales_lines(edited_lines),
        material="材质", color="颜色", size="尺码", leading=["品牌"],
    )
    if lines.empty:
        st.info("添加销售 SKU、数量和单价后，这里会显示 Invoice 汇总。")
        return
    total_quantity = int(lines["数量"].sum())
    subtotal = float(lines["金额"].sum())
    metrics = st.columns(3)
    metrics[0].metric("SKU 明细", f"{len(lines):,}")
    metrics[1].metric("销售数量", f"{total_quantity:,}")
    metrics[2].metric("Invoice 金额", f"${subtotal:,.2f}")

    inventory = load_outbound_inventory(supabase, department, category)
    if combine_brands:
        adjustments, issues = allocate_brand_merged_sales(
            lines, inventory, invoice_date, invoice_number
        )
    else:
        adjustments = build_sales_adjustments(
            lines, invoice_date, invoice_number
        )
        issues = find_outbound_inventory_issues(adjustments, inventory)
    render_inventory_change_comparison(
        build_inventory_change_comparison(inventory, adjustments),
        action="扣减", title="销售出库库存核对",
    )
    if not issues.empty:
        st.error("销售出库包含无效 SKU 或库存不足，尚不能生成 Invoice。")
        st.dataframe(issues, hide_index=True, width="stretch")
        return

    invoice_payload = {
        "tenant_code": "default",
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "department": department,
        "category": category,
        "currency": "USD",
        "note": note,
    }
    render_invoice_review(
        supabase, edited_company, edited_customer, invoice_payload, lines,
        adjustments, total_quantity, version,
    )
