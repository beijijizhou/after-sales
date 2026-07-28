alter table public.inventory_container_imports
add column if not exists actual_arrival_at timestamptz;

alter table public.inventory_container_events
add column if not exists actual_arrival_at timestamptz;

update public.inventory_container_imports
set actual_arrival_at =
    actual_arrival_date::timestamp at time zone 'America/New_York'
where actual_arrival_at is null
  and actual_arrival_date is not null;

create index if not exists inventory_container_imports_actual_arrival_at_idx
on public.inventory_container_imports (actual_arrival_at desc);

notify pgrst, 'reload schema';
