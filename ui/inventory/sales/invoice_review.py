"""Preview and final commit of a validated sales invoice."""

import streamlit as st

from db.inventory.sales import build_sales_draft_signature, build_sales_invoice_pdf, save_sales_invoice
from ui.inventory.sales.pdf_preview import render_invoice_pdf_preview
from utils.auth import get_current_operator_name


def render_invoice_review(supabase, company, customer, payload, lines, adjustments, total_quantity, version):
    number = payload["invoice_number"]
    signature = build_sales_draft_signature(company, customer, payload, lines)
    preview_key = f"sales_invoice_preview_{version}"
    if st.button("预览 Invoice", width="stretch", key=f"preview_sales_invoice_{version}"):
        if not str(company.get("company_name") or "").strip():
            st.error("我方公司名称不能为空。")
            return
        if not str(customer.get("display_name") or "").strip():
            st.error("客户名称不能为空。")
            return
        st.session_state[preview_key] = {"signature": signature, "pdf": build_sales_invoice_pdf({**payload, "status": "draft"}, company, customer, lines)}
        st.rerun()
    preview = st.session_state.get(preview_key)
    if not preview:
        st.info("请先预览 Invoice；预览确认后才会开放正式生成按钮。")
        return
    if preview.get("signature") != signature:
        st.warning("Invoice 内容已修改，请重新预览后再确认生成。")
        return
    st.markdown("#### Invoice 预览")
    render_invoice_pdf_preview(preview["pdf"])
    st.download_button("下载预览 PDF", data=preview["pdf"], file_name=f"{number}-DRAFT.pdf", mime="application/pdf", key=f"download_sales_preview_{version}")
    confirmed = st.checkbox("我已核对客户、SKU、数量、单价和总金额", key=f"confirm_sales_preview_{version}")
    st.warning("确认后会立即扣减库存并正式签发 Invoice。")
    if not st.button("确认销售出库并生成正式 Invoice", type="primary", width="stretch", disabled=not confirmed, key=f"confirm_sales_invoice_{version}"):
        return
    try:
        _, saved_lines = save_sales_invoice(supabase, company, customer, payload, lines, get_current_operator_name(), inventory_adjustments=adjustments)
        pdf = build_sales_invoice_pdf({"invoice_number": number, "invoice_date": payload["invoice_date"], "note": payload["note"]}, company, customer, saved_lines)
        st.session_state["sales_invoice_download"] = {"number": number, "pdf": pdf}
        st.session_state["sales_invoice_version"] = version + 1
        st.session_state.pop(preview_key, None)
        st.session_state["inventory_saved_message"] = f"Invoice {number} 已生成；已销售出库 {total_quantity:,} 件。"
        st.rerun()
    except Exception as error:
        st.error(f"销售出库失败：{error}")
