"""Company and customer selection for sales invoices."""

import streamlit as st

from db.inventory.sales import save_company_profile, save_customer
from ui.inventory.sales.forms import customer_from_row, render_company_table, render_customer_table
from utils.auth import get_current_operator_name


EMPTY_CUSTOMER = {"customer_type": "company", "display_name": "", "contact_name": "", "email": "", "phone": "", "address_line1": "", "city": "", "state": "", "postal_code": "", "country": "USA"}


def render_sales_parties(supabase, company, customers, version):
    with st.expander("我方公司资料", expanded=False):
        edited_company = render_company_table(company)
        if st.button("保存我方公司资料", key="save_sales_company"):
            try:
                save_company_profile(supabase, edited_company)
                st.success("我方公司资料已保存。")
            except Exception:
                st.error("公司资料保存失败，请检查必填内容。")
    st.markdown("#### 客户资料")
    lookup = _customer_lookup(customers)
    selected = st.selectbox("选择已保存客户或新建客户", ["+ 新客户", *lookup], key="sales_customer_selection")
    row = lookup.get(selected)
    customer = customer_from_row(row) if row is not None else EMPTY_CUSTOMER.copy()
    customer_version = f"{version}_{customer.get('id') or 'new'}"
    edited_customer = render_customer_table(customer, customer_version)
    if st.button("保存客户资料", key=f"save_customer_{customer_version}"):
        try:
            save_customer(supabase, edited_customer, get_current_operator_name())
            st.session_state["inventory_saved_message"] = "客户资料已保存。"
            st.rerun()
        except Exception:
            st.error("客户资料保存失败；客户名称不能为空。")
    return edited_company, edited_customer


def _customer_lookup(customers):
    lookup = {}
    for _, row in customers.iterrows():
        details = str(row.get("contact_name") or row.get("email") or "").strip()
        label = str(row["display_name"])
        if details:
            label = f"{label}｜{details}"
        if label in lookup:
            label = f"{label}｜{str(row['id'])[:8]}"
        lookup[label] = row
    return lookup
