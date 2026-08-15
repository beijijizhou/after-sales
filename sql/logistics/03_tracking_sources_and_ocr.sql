begin;

create table if not exists public.logistics_tracking_check_sources (
    id uuid primary key default gen_random_uuid(),
    check_id uuid not null
        references public.logistics_tracking_checks(id) on delete cascade,
    shipment_id uuid not null
        references public.logistics_shipments(id) on delete cascade,
    department text not null default '',
    erp_platform text not null,
    erp_account text not null,
    external_order_id text not null default '',
    merchant_order_id text not null default '',
    label_url text,
    backup_label_url text,
    created_at timestamptz not null default now(),
    constraint logistics_tracking_check_source_unique
        unique (check_id, shipment_id)
);

create index if not exists logistics_tracking_sources_check_idx
    on public.logistics_tracking_check_sources (check_id);
create index if not exists logistics_tracking_sources_shipment_idx
    on public.logistics_tracking_check_sources (shipment_id);
create index if not exists logistics_tracking_sources_scope_idx
    on public.logistics_tracking_check_sources (
        department, erp_platform, erp_account, created_at desc
    );

alter table public.logistics_label_reviews
    add column if not exists label_url text,
    add column if not exists ocr_status text not null default '',
    add column if not exists ocr_error text,
    add column if not exists ocr_engine_version text not null default '';

create index if not exists logistics_label_reviews_latest_idx
    on public.logistics_label_reviews (shipment_id, created_at desc);

grant select, insert, update on public.logistics_tracking_check_sources
    to service_role;
grant select, insert on public.logistics_label_reviews
    to service_role;

commit;

notify pgrst, 'reload schema';
