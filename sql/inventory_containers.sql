create table if not exists public.inventory_container_imports (
    id uuid primary key default gen_random_uuid(),
    container_key text not null,
    shipped_date date not null,
    expected_arrival_date date not null,
    actual_arrival_date date,
    container_no text,
    department text not null default 'DTF',
    category text,
    brand text not null default '',
    material text not null default '',
    color text not null,
    size text not null,
    quantity integer not null check (quantity >= 0),
    unit_cost numeric(10, 2) not null default 0,
    品牌 text not null default '',
    材质 text not null default '',
    成本 numeric(10, 2) not null default 0,
    status text not null default '未到货',
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.inventory_container_imports
add column if not exists container_key text,
add column if not exists shipped_date date,
add column if not exists actual_arrival_date date,
add column if not exists department text,
add column if not exists brand text,
add column if not exists material text,
add column if not exists color text,
add column if not exists size text,
add column if not exists unit_cost numeric(10, 2),
add column if not exists 品牌 text,
add column if not exists 材质 text,
add column if not exists 成本 numeric(10, 2);

update public.inventory_container_imports
set
    container_key = coalesce(
        container_key,
        nullif(regexp_replace(upper(container_no), '\s+', '', 'g'), ''),
        id::text
    ),
    shipped_date = coalesce(shipped_date, expected_arrival_date - 45),
    department = coalesce(nullif(department, ''), 'DTF'),
    brand = coalesce(brand, 品牌, ''),
    material = coalesce(material, 材质, ''),
    color = coalesce(color, ''),
    size = coalesce(size, ''),
    unit_cost = coalesce(unit_cost, 成本, 0);

alter table public.inventory_container_imports
alter column department set default 'DTF',
alter column brand set default '',
alter column material set default '',
alter column color set default '',
alter column size set default '',
alter column unit_cost set default 0;

alter table public.inventory_container_imports
alter column container_key set not null,
alter column shipped_date set not null,
alter column department set not null,
alter column brand set not null,
alter column material set not null,
alter column color set not null,
alter column size set not null,
alter column unit_cost set not null;

alter table public.inventory_container_imports
alter column category drop not null;

create index if not exists inventory_container_imports_arrival_idx
on public.inventory_container_imports (expected_arrival_date);

create index if not exists inventory_container_imports_key_idx
on public.inventory_container_imports (container_key);

create index if not exists inventory_container_imports_shipped_idx
on public.inventory_container_imports (shipped_date);

comment on column public.inventory_container_imports.shipped_date
is '实际或计划发货日期；预计到货日期通常按发货日期加45天计算';

create index if not exists inventory_container_imports_sku_idx
on public.inventory_container_imports (department, category, brand, material, color, size);

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

create or replace function public.touch_inventory_container_imports_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists inventory_container_imports_touch_updated_at on public.inventory_container_imports;

create trigger inventory_container_imports_touch_updated_at
before update on public.inventory_container_imports
for each row
execute function public.touch_inventory_container_imports_updated_at();

grant select, insert, update on public.inventory_container_imports to anon;
grant select, insert, update on public.inventory_container_imports to authenticated;
grant select, insert, update on public.inventory_container_imports to service_role;

grant select, insert on public.inventory_container_events to anon;
grant select, insert on public.inventory_container_events to authenticated;
grant select, insert on public.inventory_container_events to service_role;

notify pgrst, 'reload schema';
