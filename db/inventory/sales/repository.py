import pandas as pd


DEFAULT_COMPANY_PROFILE = {
    "tenant_code": "default",
    "profile_code": "main",
    "company_name": "Haloo",
    "email": "admin@haloousa.com",
    "phone": "",
    "address_line1": "25 ranick road",
    "city": "Happuage",
    "state": "NY",
    "postal_code": "11788",
    "country": "USA",
}


def load_company_profile(supabase, tenant_code="default"):
    rows = (
        supabase.table("inventory_company_profiles")
        .select("*")
        .eq("tenant_code", tenant_code)
        .eq("profile_code", "main")
        .limit(1)
        .execute()
        .data or []
    )
    return {**DEFAULT_COMPANY_PROFILE, **(rows[0] if rows else {})}


def save_company_profile(supabase, profile):
    payload = {**DEFAULT_COMPANY_PROFILE, **profile}
    payload.pop("id", None)
    response = (
        supabase.table("inventory_company_profiles")
        .upsert(payload, on_conflict="tenant_code,profile_code")
        .execute()
    )
    return (response.data or [payload])[0]


def load_customers(supabase, tenant_code="default"):
    columns = (
        "id,customer_type,display_name,contact_name,email,phone,"
        "address_line1,city,state,postal_code,country,is_active"
    )
    rows = (
        supabase.table("inventory_customers")
        .select(columns)
        .eq("tenant_code", tenant_code)
        .eq("is_active", True)
        .order("display_name")
        .execute()
        .data or []
    )
    return pd.DataFrame(rows)


def save_customer(supabase, customer, created_by, tenant_code="default"):
    payload = {
        **customer,
        "tenant_code": tenant_code,
        "created_by": created_by,
        "updated_at": "now()",
    }
    customer_id = payload.pop("id", None)
    payload.pop("updated_at", None)
    if customer_id:
        response = (
            supabase.table("inventory_customers")
            .update(payload)
            .eq("id", customer_id)
            .eq("tenant_code", tenant_code)
            .execute()
        )
    else:
        response = supabase.table("inventory_customers").insert(payload).execute()
    return (response.data or [{}])[0]


def load_sales_invoices(supabase, tenant_code="default", limit=100):
    rows = (
        supabase.table("inventory_sales_invoices")
        .select(
            "id,invoice_number,inventory_batch_id,invoice_date,currency,"
            "subtotal,status,note,created_by,created_at,"
            "inventory_customers(display_name,contact_name,email,phone)"
        )
        .eq("tenant_code", tenant_code)
        .order("invoice_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    return pd.DataFrame(rows)


def load_invoice_detail(supabase, invoice_id):
    invoice_rows = (
        supabase.table("inventory_sales_invoices")
        .select(
            "*,inventory_company_profiles(*),inventory_customers(*)"
        )
        .eq("id", str(invoice_id))
        .limit(1)
        .execute()
        .data or []
    )
    if not invoice_rows:
        return None, pd.DataFrame()
    lines = (
        supabase.table("inventory_sales_invoice_lines")
        .select("*")
        .eq("invoice_id", str(invoice_id))
        .order("line_number")
        .execute()
        .data or []
    )
    return invoice_rows[0], pd.DataFrame(lines)


def void_sales_invoice(supabase, invoice_id, created_by):
    return supabase.rpc("void_inventory_sales_invoice", {
        "p_invoice_id": str(invoice_id),
        "p_created_by": created_by,
    }).execute().data
