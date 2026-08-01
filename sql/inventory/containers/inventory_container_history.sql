ImportError: cannot import name 'build_container_history_display' from 'db.inventory.container' (/Users/hongzhonghu/Desktop/after-sales/db/inventory/container/__init__.py)alter table public.inventory_container_imports
add column if not exists container_key text,
add column if not exists actual_arrival_date date;

update public.inventory_container_imports
set container_key = coalesce(
    container_key,
    nullif(regexp_replace(upper(container_no), '\s+', '', 'g'), ''),
    id::text
)
where container_key is null;

alter table public.inventory_container_imports
alter column container_key set not null;

create index if not exists inventory_container_imports_key_idx
on public.inventory_container_imports (container_key);

create table if not exists public.inventory_container_events (
    id uuid primary key default gen_random_uuid(),
    container_key text not null,
    container_no text,
    event_type text not null,
    effective_date date not null,
    previous_status text,
    new_status text,
    operated_by text not null default 'system',
    note text,
    created_at timestamptz not null default now()
);

create index if not exists inventory_container_events_lookup_idx
on public.inventory_container_events (container_key, effective_date desc, created_at desc);

grant select, insert on public.inventory_container_events to anon;
grant select, insert on public.inventory_container_events to authenticated;
grant select, insert on public.inventory_container_events to service_role;

update public.inventory_container_imports
set
    status = '已到货',
    actual_arrival_date = date '2026-07-14'
where container_key = 'COSU9507559000';

insert into public.inventory_container_events (
    container_key,
    container_no,
    event_type,
    effective_date,
    previous_status,
    new_status,
    operated_by,
    note
)
select
    'COSU9507559000',
    max(container_no),
    '到货',
    date '2026-07-14',
    '未到货',
    '已到货',
    'Andy',
    '货柜已到货，库存已入库'
from public.inventory_container_imports
where container_key = 'COSU9507559000'
having count(*) > 0
   and not exists (
       select 1
       from public.inventory_container_events event
       where event.container_key = 'COSU9507559000'
         and event.event_type = '到货'
         and event.effective_date = date '2026-07-14'
   );

notify pgrst, 'reload schema';
