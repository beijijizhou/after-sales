begin;

create table if not exists public.logistics_usps_usage_events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null default 'query'
        check (event_type in ('query', 'baseline')),
    tracking_count integer not null default 0 check (tracking_count >= 0),
    request_count integer not null default 0 check (request_count >= 0),
    successful_count integer not null default 0 check (successful_count >= 0),
    failed_count integer not null default 0 check (failed_count >= 0),
    official_count integer check (official_count >= 0),
    created_by text not null default 'system',
    created_at timestamptz not null default now()
);

drop index if exists public.logistics_usps_usage_month_idx;

alter table public.logistics_usps_usage_events
    drop column if exists tenant_code;

create index if not exists logistics_usps_usage_created_idx
    on public.logistics_usps_usage_events (created_at desc);

create index if not exists logistics_usps_usage_user_idx
    on public.logistics_usps_usage_events (created_by, created_at desc);

commit;
