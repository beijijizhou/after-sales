begin;

create table if not exists public.inventory_company_profiles (
    id uuid primary key default gen_random_uuid(),
    tenant_code text not null default 'default',
    profile_code text not null default 'main',
    company_name text not null,
    email text,
    phone text,
    address_line1 text,
    city text,
    state text,
    postal_code text,
    country text not null default 'USA',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_code, profile_code)
);

create table if not exists public.inventory_customers (
    id uuid primary key default gen_random_uuid(),
    tenant_code text not null default 'default',
    customer_type text not null check (customer_type in ('company', 'person')),
    display_name text not null,
    contact_name text,
    email text,
    phone text,
    address_line1 text,
    city text,
    state text,
    postal_code text,
    country text not null default 'USA',
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists inventory_customers_tenant_name_idx
on public.inventory_customers (tenant_code, display_name);

create table if not exists public.inventory_sales_invoices (
    id uuid primary key default gen_random_uuid(),
    tenant_code text not null default 'default',
    invoice_number text not null,
    inventory_batch_id uuid not null unique,
    company_profile_id uuid not null references public.inventory_company_profiles(id),
    customer_id uuid not null references public.inventory_customers(id),
    company_snapshot jsonb not null,
    customer_snapshot jsonb not null,
    department text not null,
    category text not null,
    invoice_date date not null,
    currency text not null default 'USD',
    subtotal numeric(14, 2) not null check (subtotal >= 0),
    status text not null default 'issued' check (status in ('draft', 'issued', 'void')),
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    unique (tenant_code, invoice_number)
);

create table if not exists public.inventory_sales_invoice_lines (
    id uuid primary key default gen_random_uuid(),
    invoice_id uuid not null references public.inventory_sales_invoices(id) on delete restrict,
    line_number integer not null,
    brand text not null default '',
    material text not null,
    color text not null,
    size text not null,
    quantity integer not null check (quantity > 0),
    unit_price numeric(14, 4) not null check (unit_price >= 0),
    line_total numeric(14, 2) generated always as (round(quantity * unit_price, 2)) stored,
    unique (invoice_id, line_number)
);

create index if not exists inventory_sales_invoices_date_idx
on public.inventory_sales_invoices (tenant_code, invoice_date desc, created_at desc);

alter table public.inventory_sales_invoices
add column if not exists company_snapshot jsonb;
alter table public.inventory_sales_invoices
add column if not exists customer_snapshot jsonb;

create or replace function public.create_inventory_sales_invoice(
    p_company jsonb,
    p_customer jsonb,
    p_invoice jsonb,
    p_lines jsonb,
    p_inventory_rows jsonb,
    p_created_by text default 'system'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    effective_tenant text := coalesce(nullif(trim(p_invoice->>'tenant_code'), ''), 'default');
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
    company_id uuid;
    customer_id uuid;
    requested_customer_id uuid;
    invoice_id uuid := gen_random_uuid();
    batch_id uuid := gen_random_uuid();
    line_row jsonb;
    calculated_subtotal numeric(14, 2) := 0;
begin
    if jsonb_typeof(p_lines) <> 'array' or jsonb_array_length(p_lines) = 0 then
        raise exception '销售出库明细不能为空';
    end if;

    insert into public.inventory_company_profiles (
        tenant_code, profile_code, company_name, email, phone,
        address_line1, city, state, postal_code, country, updated_at
    ) values (
        effective_tenant,
        coalesce(nullif(trim(p_company->>'profile_code'), ''), 'main'),
        trim(p_company->>'company_name'), nullif(trim(p_company->>'email'), ''),
        nullif(trim(p_company->>'phone'), ''), nullif(trim(p_company->>'address_line1'), ''),
        nullif(trim(p_company->>'city'), ''), nullif(trim(p_company->>'state'), ''),
        nullif(trim(p_company->>'postal_code'), ''),
        coalesce(nullif(trim(p_company->>'country'), ''), 'USA'), now()
    )
    on conflict (tenant_code, profile_code) do update set
        company_name = excluded.company_name,
        email = excluded.email,
        phone = excluded.phone,
        address_line1 = excluded.address_line1,
        city = excluded.city,
        state = excluded.state,
        postal_code = excluded.postal_code,
        country = excluded.country,
        updated_at = now()
    returning id into company_id;

    requested_customer_id := nullif(p_customer->>'id', '')::uuid;
    if requested_customer_id is null then
        insert into public.inventory_customers (
            tenant_code, customer_type, display_name, contact_name,
            email, phone, address_line1, city, state, postal_code,
            country, created_by
        ) values (
            effective_tenant, p_customer->>'customer_type', trim(p_customer->>'display_name'),
            nullif(trim(p_customer->>'contact_name'), ''), nullif(trim(p_customer->>'email'), ''),
            nullif(trim(p_customer->>'phone'), ''), nullif(trim(p_customer->>'address_line1'), ''),
            nullif(trim(p_customer->>'city'), ''), nullif(trim(p_customer->>'state'), ''),
            nullif(trim(p_customer->>'postal_code'), ''),
            coalesce(nullif(trim(p_customer->>'country'), ''), 'USA'), effective_user
        ) returning id into customer_id;
    else
        update public.inventory_customers set
            customer_type = p_customer->>'customer_type',
            display_name = trim(p_customer->>'display_name'),
            contact_name = nullif(trim(p_customer->>'contact_name'), ''),
            email = nullif(trim(p_customer->>'email'), ''),
            phone = nullif(trim(p_customer->>'phone'), ''),
            address_line1 = nullif(trim(p_customer->>'address_line1'), ''),
            city = nullif(trim(p_customer->>'city'), ''),
            state = nullif(trim(p_customer->>'state'), ''),
            postal_code = nullif(trim(p_customer->>'postal_code'), ''),
            country = coalesce(nullif(trim(p_customer->>'country'), ''), 'USA'),
            updated_at = now()
        where id = requested_customer_id and tenant_code = effective_tenant
        returning id into customer_id;
        if customer_id is null then
            raise exception '客户资料不存在或不属于当前公司';
        end if;
    end if;

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        calculated_subtotal := calculated_subtotal + round(
            (line_row->>'quantity')::integer * (line_row->>'unit_price')::numeric,
            2
        );
    end loop;

    batch_id := public.apply_inventory_adjustment_batch(
        p_invoice->>'department', p_invoice->>'category', p_inventory_rows,
        batch_id, effective_user, 'bulk'
    );

    insert into public.inventory_sales_invoices (
        id, tenant_code, invoice_number, inventory_batch_id,
        company_profile_id, customer_id, company_snapshot, customer_snapshot,
        department, category,
        invoice_date, currency, subtotal, status, note, created_by
    ) values (
        invoice_id, effective_tenant, trim(p_invoice->>'invoice_number'), batch_id,
        company_id, customer_id, p_company, p_customer,
        p_invoice->>'department', p_invoice->>'category',
        (p_invoice->>'invoice_date')::date,
        coalesce(nullif(trim(p_invoice->>'currency'), ''), 'USD'),
        calculated_subtotal, 'issued', nullif(trim(p_invoice->>'note'), ''), effective_user
    );

    insert into public.inventory_sales_invoice_lines (
        invoice_id, line_number, brand, material, color, size, quantity, unit_price
    )
    select
        invoice_id, ordinality::integer,
        coalesce(value->>'brand', ''), value->>'material', value->>'color',
        upper(value->>'size'), (value->>'quantity')::integer,
        (value->>'unit_price')::numeric
    from jsonb_array_elements(p_lines) with ordinality;

    return jsonb_build_object(
        'invoice_id', invoice_id,
        'inventory_batch_id', batch_id,
        'customer_id', customer_id,
        'subtotal', calculated_subtotal
    );
end;
$$;

create or replace function public.void_inventory_sales_invoice(
    p_invoice_id uuid,
    p_created_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    source_invoice public.inventory_sales_invoices%rowtype;
    reversal_batch_id uuid;
begin
    select * into source_invoice
    from public.inventory_sales_invoices
    where id = p_invoice_id
    for update;
    if source_invoice.id is null then
        raise exception 'Invoice 不存在';
    end if;
    if source_invoice.status <> 'issued' then
        raise exception '只有已签发 Invoice 可以作废';
    end if;
    reversal_batch_id := public.reverse_inventory_movement_batch(
        source_invoice.inventory_batch_id,
        coalesce(nullif(trim(p_created_by), ''), 'system')
    );
    update public.inventory_sales_invoices
    set status = 'void'
    where id = source_invoice.id;
    return reversal_batch_id;
end;
$$;

grant select, insert, update on public.inventory_company_profiles to authenticated, service_role;
grant select, insert, update on public.inventory_customers to authenticated, service_role;
grant select, insert on public.inventory_sales_invoices to authenticated, service_role;
grant select, insert on public.inventory_sales_invoice_lines to authenticated, service_role;
grant execute on function public.create_inventory_sales_invoice(
    jsonb, jsonb, jsonb, jsonb, jsonb, text
) to authenticated, service_role;
grant execute on function public.void_inventory_sales_invoice(uuid, text)
to authenticated, service_role;

commit;
notify pgrst, 'reload schema';
