import pandas as pd
import streamlit as st


COMPANY_COLUMNS = {
    "company_name": "公司名称",
    "email": "邮箱",
    "phone": "电话",
    "address_line1": "街道地址",
    "city": "城市",
    "state": "州",
    "postal_code": "邮编",
    "country": "国家",
}
CUSTOMER_COLUMNS = {
    "customer_type": "客户类型",
    "display_name": "公司 / 个人名称",
    "contact_name": "联系人",
    "email": "邮箱",
    "phone": "电话",
    "address_line1": "街道地址",
    "city": "城市",
    "state": "州",
    "postal_code": "邮编",
    "country": "国家",
}


def render_company_table(profile):
    source = pd.DataFrame([{
        label: profile.get(key, "") for key, label in COMPANY_COLUMNS.items()
    }])
    edited = st.data_editor(
        source, hide_index=True, width="stretch", num_rows="fixed",
        key="sales_company_profile_editor",
    )
    row = edited.iloc[0].to_dict()
    return {
        **profile,
        **{key: _clean(row.get(label)) for key, label in COMPANY_COLUMNS.items()},
    }


def render_customer_table(customer, version):
    source = pd.DataFrame([{
        label: customer.get(key, "") for key, label in CUSTOMER_COLUMNS.items()
    }])
    source["客户类型"] = source["客户类型"].replace({
        "company": "公司", "person": "个人",
    })
    edited = st.data_editor(
        source, hide_index=True, width="stretch", num_rows="fixed",
        column_config={
            "客户类型": st.column_config.SelectboxColumn(
                "客户类型", options=["公司", "个人"], required=True,
            ),
        },
        key=f"sales_customer_editor_{version}",
    )
    row = edited.iloc[0].to_dict()
    customer_type = "person" if row.get("客户类型") == "个人" else "company"
    return {
        **customer,
        **{
            key: _clean(row.get(label))
            for key, label in CUSTOMER_COLUMNS.items()
            if key != "customer_type"
        },
        "customer_type": customer_type,
    }


def customer_from_row(row):
    return {
        key: row.get(key, "")
        for key in ["id", *CUSTOMER_COLUMNS]
    }


def _clean(value):
    return "" if pd.isna(value) else str(value).strip()
