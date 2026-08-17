begin;

create table if not exists public.production_platform_daily_consumption (
    business_date date not null,
    department text not null,
    category text not null,
    platform text not null,
    color text not null,
    size text not null,
    quantity integer not null check (quantity >= 0),
    record_count integer not null default 0 check (record_count >= 0),
    source text not null default 'ERP/API',
    fetched_at timestamptz not null default now(),
    primary key (
        business_date, department, category, platform, color, size
    )
);

create index if not exists production_daily_consumption_lookup
    on public.production_platform_daily_consumption (
        department, category, business_date, platform
    );

create table if not exists public.production_consumption_sync_batches (
    id uuid primary key default gen_random_uuid(),
    department text not null,
    category text not null,
    platform text not null,
    start_date date not null,
    end_date date not null,
    source text not null default 'ERP/API',
    row_count integer not null default 0,
    total_quantity integer not null default 0,
    operator text not null default 'system',
    status text not null default 'completed',
    created_at timestamptz not null default now()
);

grant select on public.production_platform_daily_consumption
    to anon, authenticated, service_role;
grant select on public.production_consumption_sync_batches
    to authenticated, service_role;

commit;
