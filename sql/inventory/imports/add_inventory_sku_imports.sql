create table if not exists public.inventory_sku_imports (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    品牌 text not null default '',
    材质 text not null default '180g',
    color text not null,
    size text not null,
    initial_quantity integer not null default 0 check (initial_quantity >= 0),
    成本 numeric(10, 2) not null default 0,
    import_date date not null default current_date,
    created_at timestamptz not null default now()
);

alter table public.inventory_sku_imports
add column if not exists 材质 text not null default '180g';

alter table public.inventory_sku_imports
add column if not exists 品牌 text not null default '';

alter table public.inventory_sku_imports
add column if not exists 成本 numeric(10, 2) not null default 0;

grant select, insert on public.inventory_sku_imports to anon;
grant select, insert on public.inventory_sku_imports to authenticated;
grant select, insert on public.inventory_sku_imports to service_role;

notify pgrst, 'reload schema';
