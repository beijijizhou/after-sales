begin;

create table if not exists public.logistics_shipments (
    id uuid primary key default gen_random_uuid(),
    tenant_code text not null default 'default',
    erp_platform text not null,
    erp_account text not null,
    department text not null default '',
    external_order_id text not null,
    merchant_order_id text not null default '',
    tracking_number text not null default '',
    carrier text not null default '',
    erp_status text not null default '',
    label_url text,
    backup_label_url text,
    local_acceptance_status text not null default '未接单',
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    source_payload jsonb not null default '{}'::jsonb,
    constraint logistics_shipments_identity_unique unique (
        tenant_code, erp_platform, erp_account, external_order_id,
        tracking_number
    )
);

create index if not exists logistics_shipments_tracking_idx
    on public.logistics_shipments (tenant_code, tracking_number);
create index if not exists logistics_shipments_pending_idx
    on public.logistics_shipments (
        tenant_code, local_acceptance_status, last_seen_at desc
    );

create table if not exists public.logistics_tracking_checks (
    id uuid primary key default gen_random_uuid(),
    tenant_code text not null default 'default',
    tracking_number text not null,
    provider text not null default 'USPS',
    checked_at timestamptz not null default now(),
    cache_expires_at timestamptz not null,
    provider_status text not null default '',
    has_postal_record boolean not null default false,
    has_pre_scan boolean not null default false,
    response_payload jsonb not null default '{}'::jsonb,
    error_code text,
    created_by text not null default 'system'
);

create index if not exists logistics_tracking_checks_latest_idx
    on public.logistics_tracking_checks (
        tenant_code, tracking_number, checked_at desc
    );

create table if not exists public.logistics_label_reviews (
    id uuid primary key default gen_random_uuid(),
    shipment_id uuid not null references public.logistics_shipments(id),
    label_content_hash text,
    extracted_street text,
    extracted_city text,
    extracted_state text,
    extracted_postal_code text,
    extracted_weight_oz numeric(12, 3),
    rule_version text not null default 'draft-v1',
    automatic_result text not null default '待识别',
    automatic_reasons jsonb not null default '[]'::jsonb,
    reviewer_result text,
    reviewer_note text,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

commit;
