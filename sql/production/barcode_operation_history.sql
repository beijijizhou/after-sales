create extension if not exists pgcrypto;

create table if not exists public.barcode_operation_history (
    id uuid primary key default gen_random_uuid(),
    barcode text not null,
    platform text,
    operation_type text not null,
    reason text,
    note text,
    requires_rescan boolean not null default true,
    created_by text not null,
    created_at timestamptz not null default now()
);

alter table public.barcode_operation_history
add column if not exists platform text;

create table if not exists public.platforms (
    name text primary key,
    is_active boolean not null default true,
    sort_order integer not null default 0,
    created_at timestamptz not null default now()
);

insert into public.platforms (name, sort_order)
values
    ('Haloo', 10),
    ('S2B', 20),
    ('汉森', 30),
    ('隆丰', 40),
    ('SDS', 50),
    ('一朵云', 60),
    ('七创', 70),
    ('莆田', 80),
    ('方果', 90),
    ('必印', 100),
    ('赛博', 110),
    ('中昌', 120),
    ('RBT', 130),
    ('卖途', 140),
    ('Example', 150),
    ('全球定制', 160),
    ('托易通', 170),
    ('闪印', 180),
    ('POD Vision Himytool', 190)
on conflict (name) do update
set sort_order = excluded.sort_order;

drop function if exists public.get_barcode_platform_options();

create index if not exists idx_barcode_operation_history_barcode
on public.barcode_operation_history (upper(trim(barcode)));

create index if not exists idx_barcode_operation_history_barcode_created_at
on public.barcode_operation_history (barcode, created_at);

create index if not exists idx_barcode_operation_history_requires_rescan
on public.barcode_operation_history (requires_rescan, created_at desc);

create index if not exists idx_barcode_operation_history_created_at
on public.barcode_operation_history (created_at desc);

create index if not exists idx_barcode_scans_barcode_scanned_at
on public.barcode_scans (barcode, scanned_at);

grant select, insert on public.barcode_operation_history to anon;
grant select, insert on public.barcode_operation_history to authenticated;
grant select, insert on public.barcode_operation_history to service_role;

grant select on public.platforms to anon;
grant select on public.platforms to authenticated;
grant select, insert, update on public.platforms to service_role;

notify pgrst, 'reload schema';
