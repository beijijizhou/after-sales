from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.operations.outbound_audit import (
    find_outbound_inventory_issues,
    load_outbound_inventory,
)
from db.inventory.sales import (
    allocate_brand_merged_sales,
    build_invoice_number,
    build_sales_adjustments,
    build_sales_draft_signature,
    build_sales_invoice_pdf,
    load_company_profile,
    load_customers,
    load_sales_invoices,
    normalize_sales_lines,
    save_company_profile,
    save_customer,
    save_sales_invoice,
)
from ui.inventory.sales.forms import (
    customer_from_row,
    render_company_table,
    render_customer_table,
)
from ui.inventory.sales.history import render_invoice_history
from ui.inventory.sales.pdf_preview import render_invoice_pdf_preview
from ui.inventory.shared.linked_sku_table import (
    render_linked_sku_sales_table,
)
from utils.auth import get_current_operator_name
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
    with st.expander("我方公司资料", expanded=False):
        edited_company = render_company_table(company)
        if st.button("保存我方公司资料", key="save_sales_company"):
            try:
                save_company_profile(supabase, edited_company)
                st.success("我方公司资料已保存。")
            except Exception:
                st.error("公司资料保存失败，请检查必填内容。")

    st.markdown("#### 客户资料")
    customer_lookup = {}
    if not customers.empty:
        for _, row in customers.iterrows():
            details = str(row.get("contact_name") or row.get("email") or "").strip()
            label = str(row["display_name"])
            if details:
                label = f"{label}｜{details}"
            if label in customer_lookup:
                label = f"{label}｜{str(row['id'])[:8]}"
            customer_lookup[label] = row
    customer_options = ["+ 新客户", *customer_lookup]
    selected = st.selectbox(
        "选择已保存客户或新建客户",
        customer_options,
        key="sales_customer_selection",
    )
    selected_row = customer_lookup.get(selected)
    customer = customer_from_row(selected_row) if selected_row is not None else {
        "customer_type": "company", "display_name": "", "contact_name": "",
        "email": "", "phone": "", "address_line1": "", "city": "",
        "state": "", "postal_code": "", "country": "USA",
    }
    customer_version = f"{version}_{customer.get('id') or 'new'}"
    edited_customer = render_customer_table(customer, customer_version)
    if st.button("保存客户资料", key=f"save_customer_{customer_version}"):
        try:
            save_customer(
                supabase, edited_customer, get_current_operator_name()
            )
            st.session_state["inventory_saved_message"] = "客户资料已保存。"
            st.rerun()
        except Exception:
            st.error("客户资料保存失败；客户名称不能为空。")

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
    draft_signature = build_sales_draft_signature(
        edited_company, edited_customer, invoice_payload, lines
    )
    preview_key = f"sales_invoice_preview_{version}"
    if st.button(
        "预览 Invoice",
        width="stretch",
        key=f"preview_sales_invoice_{version}",
    ):
        if not str(edited_company.get("company_name") or "").strip():
            st.error("我方公司名称不能为空。")
            return
        if not str(edited_customer.get("display_name") or "").strip():
            st.error("客户名称不能为空。")
            return
        preview_pdf = build_sales_invoice_pdf(
            {
                **invoice_payload,
                "status": "draft",
            },
            edited_company,
            edited_customer,
            lines,
        )
        st.session_state[preview_key] = {
            "signature": draft_signature,
            "pdf": preview_pdf,
        }
        st.rerun()

    preview = st.session_state.get(preview_key)
    if not preview:
        st.info("请先预览 Invoice；预览确认后才会开放正式生成按钮。")
        return
    if preview.get("signature") != draft_signature:
        st.warning("Invoice 内容已修改，请重新预览后再确认生成。")
        return
    st.markdown("#### Invoice 预览")
    render_invoice_pdf_preview(preview["pdf"])
    st.download_button(
        "下载预览 PDF",
        data=preview["pdf"],
        file_name=f"{invoice_number}-DRAFT.pdf",
        mime="application/pdf",
        key=f"download_sales_preview_{version}",
    )
    confirmed = st.checkbox(
        "我已核对客户、SKU、数量、单价和总金额",
        key=f"confirm_sales_preview_{version}",
    )
    st.warning("确认后会立即扣减库存并正式签发 Invoice。")
    if not st.button(
        "确认销售出库并生成正式 Invoice",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key=f"confirm_sales_invoice_{version}",
    ):
        return
    try:
        result, saved_lines = save_sales_invoice(
            supabase,
            edited_company,
            edited_customer,
            invoice_payload,
            lines,
            get_current_operator_name(),
            inventory_adjustments=adjustments,
        )
        pdf = build_sales_invoice_pdf(
            {"invoice_number": invoice_number, "invoice_date": invoice_date, "note": note},
            edited_company, edited_customer, saved_lines,
        )
        st.session_state["sales_invoice_download"] = {
            "number": invoice_number, "pdf": pdf,
        }
        st.session_state["sales_invoice_version"] = version + 1
        st.session_state.pop(preview_key, None)
        st.session_state["inventory_saved_message"] = (
            f"Invoice {invoice_number} 已生成；已销售出库 {total_quantity:,} 件。"
        )
        st.rerun()
    except Exception as error:
        st.error(f"销售出库失败：{error}")
