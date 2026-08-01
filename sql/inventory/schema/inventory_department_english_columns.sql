-- Inventory schema migration draft.
-- Goal:
-- 1. Add department as the top-level inventory grouping.
-- 2. Keep category optional because it is a manual reporting/display group.
-- 3. Add English column names while keeping existing Chinese columns for compatibility.
-- 4. Backfill existing apparel inventory as DTF.

begin;

create table if not exists public.inventory_container_imports (
    id uuid primary key default gen_random_uuid(),
    expected_arrival_date date not null,
    container_no text,
    category text,
    品牌 text not null default '',
    材质 text not null default '',
    color text not null default '',
    size text not null default '',
    quantity integer not null check (quantity >= 0),
    成本 numeric(10, 2) not null default 0,
    status text not null default '未到货',
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.inventory_items
add column if not exists department text,
add column if not exists brand text,
add column if not exists material text,
add column if not exists unit_cost numeric(10, 2);

alter table public.inventory_movements
add column if not exists department text,
add column if not exists brand text,
add column if not exists material text;

alter table public.inventory_sku_imports
add column if not exists department text,
add column if not exists brand text,
add column if not exists material text,
add column if not exists unit_cost numeric(10, 2);

alter table public.inventory_container_imports
add column if not exists department text,
add column if not exists brand text,
add column if not exists material text,
add column if not exists unit_cost numeric(10, 2);

update public.inventory_items
set
    department = coalesce(nullif(department, ''), 'DTF'),
    brand = coalesce(brand, 品牌, ''),
    material = coalesce(material, 材质, ''),
    unit_cost = coalesce(unit_cost, 成本, 0);

update public.inventory_movements
set
    department = coalesce(nullif(department, ''), 'DTF'),
    brand = coalesce(brand, 品牌, ''),
    material = coalesce(material, 材质, '');

update public.inventory_sku_imports
set
    department = coalesce(nullif(department, ''), 'DTF'),
    brand = coalesce(brand, 品牌, ''),
    material = coalesce(material, 材质, ''),
    unit_cost = coalesce(unit_cost, 成本, 0);

update public.inventory_container_imports
set
    department = coalesce(nullif(department, ''), 'DTF'),
    brand = coalesce(brand, 品牌, ''),
    material = coalesce(material, 材质, ''),
    unit_cost = coalesce(unit_cost, 成本, 0);

alter table public.inventory_items
alter column department set default 'DTF',
alter column brand set default '',
alter column material set default '',
alter column unit_cost set default 0;

alter table public.inventory_movements
alter column department set default 'DTF',
alter column brand set default '',
alter column material set default '';

alter table public.inventory_sku_imports
alter column department set default 'DTF',
alter column brand set default '',
alter column material set default '',
alter column unit_cost set default 0;

alter table public.inventory_container_imports
alter column department set default 'DTF',
alter column brand set default '',
alter column material set default '',
alter column unit_cost set default 0;

alter table public.inventory_items
alter column department set not null,
alter column brand set not null,
alter column material set not null,
alter column unit_cost set not null;

alter table public.inventory_movements
alter column department set not null,
alter column brand set not null,
alter column material set not null;

alter table public.inventory_sku_imports
alter column department set not null,
alter column brand set not null,
alter column material set not null,
alter column unit_cost set not null;

alter table public.inventory_container_imports
alter column department set not null,
alter column brand set not null,
alter column material set not null,
alter column unit_cost set not null;

alter table public.inventory_items
alter column category drop not null;

alter table public.inventory_movements
alter column category drop not null;

alter table public.inventory_sku_imports
alter column category drop not null;

alter table public.inventory_container_imports
alter column category drop not null;

alter table public.inventory_items
drop constraint if exists inventory_items_category_color_size_key;

alter table public.inventory_items
drop constraint if exists "inventory_items_category_材质_color_size_key";

drop index if exists public.inventory_items_category_material_color_size_key;
drop index if exists public.inventory_items_category_brand_material_color_size_key;
drop index if exists public.inventory_items_department_sku_key;

create unique index inventory_items_department_sku_key
on public.inventory_items (
    department,
    coalesce(category, ''),
    brand,
    material,
    coalesce(color, ''),
    coalesce(size, '')
);

drop index if exists public.inventory_container_imports_sku_idx;

create index if not exists inventory_container_imports_department_sku_idx
on public.inventory_container_imports (
    department,
    coalesce(category, ''),
    brand,
    material,
    coalesce(color, ''),
    coalesce(size, '')
);

notify pgrst, 'reload schema';

commit;
