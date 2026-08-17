import streamlit as st

from db.batches import BatchKind, BatchReference
from db.inventory.sales import (
    build_sales_invoice_pdf,
    load_invoice_detail,
)
from ui.batches import render_batch_reversal_action


def render_invoice_history(supabase, invoices, can_edit):
    download = st.session_state.get("sales_invoice_download")
    if download:
        st.download_button(
            f"下载 {download['number']} PDF",
            data=download["pdf"],
            file_name=f"{download['number']}.pdf",
            mime="application/pdf",
            type="primary",
        )
    if invoices.empty:
        st.info("暂无已签发 Invoice。")
        return
    summary = invoices.copy()
    summary["客户"] = summary["inventory_customers"].map(
        lambda value: (value or {}).get("display_name", "")
    )
    st.dataframe(
        summary[["invoice_date", "invoice_number", "客户", "subtotal", "status"]]
        .rename(columns={
            "invoice_date": "日期", "invoice_number": "Invoice",
            "subtotal": "金额", "status": "状态",
        }),
        hide_index=True, width="stretch",
    )
    selected = st.selectbox(
        "查看 Invoice 明细", summary["invoice_number"].tolist(),
        key="sales_invoice_history_selection",
    )
    invoice_id = summary.loc[
        summary["invoice_number"] == selected, "id"
    ].iloc[0]
    invoice, lines = load_invoice_detail(supabase, invoice_id)
    if invoice is None:
        return
    st.dataframe(lines, hide_index=True, width="stretch")
    pdf = build_sales_invoice_pdf(
        invoice,
        invoice.get("company_snapshot")
        or invoice.get("inventory_company_profiles") or {},
        invoice.get("customer_snapshot")
        or invoice.get("inventory_customers") or {},
        lines.rename(columns={
            "brand": "品牌", "material": "材质", "color": "颜色",
            "size": "尺码", "quantity": "数量", "unit_price": "单价",
            "line_total": "金额",
        }),
    )
    st.download_button(
        f"下载 {selected} PDF", data=pdf, file_name=f"{selected}.pdf",
        mime="application/pdf", key=f"download_invoice_{invoice_id}",
    )
    if can_edit and invoice.get("status") == "issued":
        _render_void_invoice(supabase, invoice_id, selected)


def _render_void_invoice(supabase, invoice_id, invoice_number):
    render_batch_reversal_action(
        supabase,
        BatchReference(BatchKind.SALES_INVOICE, invoice_id),
        key_scope="sales_invoice",
        confirmation_label="我确认作废此 Invoice，并生成库存反向批次",
        button_label="作废 Invoice 并退回库存",
        success_state_key="inventory_saved_message",
        success_message=(
            f"Invoice {invoice_number} 已作废，库存已生成反向批次。"
        ),
        error_label="Invoice 作废失败",
    )
