begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_departments (
    id uuid primary key default gen_random_uuid(),
    code text not null,
    name text not null,
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint inventory_departments_code_required
        check (trim(code) <> ''),
    constraint inventory_departments_name_required
        check (trim(name) <> '')
);

create unique index if not exists inventory_departments_code_unique
on public.inventory_departments (lower(trim(code)));

create table if not exists public.inventory_categories (
    id uuid primary key default gen_random_uuid(),
    department_id uuid not null
        references public.inventory_departments(id) on delete restrict,
    name text not null,
    specification_type text not null default 'none',
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint inventory_categories_name_required
        check (trim(name) <> ''),
    constraint inventory_categories_specification_type_check
        check (specification_type in ('size', 'model', 'none'))
);

create unique index if not exists inventory_categories_name_unique
on public.inventory_categories (department_id, lower(trim(name)));

create table if not exists public.inventory_brands (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint inventory_brands_name_required
        check (trim(name) <> '')
);

create unique index if not exists inventory_brands_name_unique
on public.inventory_brands (lower(trim(name)));

create table if not exists public.inventory_materials (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint inventory_materials_name_required
        check (trim(name) <> '')
);

create unique index if not exists inventory_materials_name_unique
on public.inventory_materials (lower(trim(name)));

create table if not exists public.inventory_category_materials (
    category_id uuid not null
        references public.inventory_categories(id) on delete cascade,
    material_id uuid not null
        references public.inventory_materials(id) on delete restrict,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    primary key (category_id, material_id)
);

alter table public.inventory_items
add column if not exists department_id uuid;

alter table public.inventory_items
add column if not exists category_id uuid;

alter table public.inventory_items
add column if not exists brand_id uuid;

alter table public.inventory_items
add column if not exists sku_code text;

alter table public.inventory_items
add column if not exists sku_name text;

alter table public.inventory_items
add column if not exists model text;

alter table public.inventory_items
add column if not exists unit text not null default '件';

alter table public.inventory_items
add column if not exists is_active boolean not null default true;

alter table public.inventory_items
add column if not exists created_by text not null default 'system';

alter table public.inventory_items
add column if not exists created_at timestamptz not null default now();

insert into public.inventory_departments (code, name)
values ('DTF', 'DTF'), ('UV', 'UV'), ('3D', '3D')
on conflict do nothing;

insert into public.inventory_departments (code, name)
select distinct trim(item.department), trim(item.department)
from public.inventory_items item
where nullif(trim(item.department), '') is not null
on conflict do nothing;

insert into public.inventory_categories (
    department_id, name, specification_type
)
select distinct
    department.id,
    trim(item.category),
    case when upper(trim(item.department)) = 'DTF'
        then 'size'
        else 'model'
    end
from public.inventory_items item
join public.inventory_departments department
  on lower(trim(department.code)) = lower(trim(item.department))
where nullif(trim(item.category), '') is not null
on conflict do nothing;

insert into public.inventory_brands (name)
select distinct trim(item.brand)
from public.inventory_items item
where nullif(trim(item.brand), '') is not null
on conflict do nothing;

insert into public.inventory_materials (name)
select distinct trim(item.material)
from public.inventory_items item
where nullif(trim(item.material), '') is not null
on conflict do nothing;

update public.inventory_items item
set department_id = department.id
from public.inventory_departments department
where item.department_id is null
  and lower(trim(department.code)) = lower(trim(item.department));

update public.inventory_items item
set category_id = category.id
from public.inventory_categories category
where item.category_id is null
  and category.department_id = item.department_id
  and lower(trim(category.name)) = lower(trim(item.category));

insert into public.inventory_category_materials (category_id, material_id)
select distinct item.category_id, material.id
from public.inventory_items item
join public.inventory_materials material
  on lower(trim(material.name)) = lower(trim(item.material))
where item.category_id is not null
  and nullif(trim(item.material), '') is not null
on conflict do nothing;

update public.inventory_items item
set brand_id = brand.id
from public.inventory_brands brand
where item.brand_id is null
  and lower(trim(brand.name)) = lower(trim(item.brand));

update public.inventory_items
set model = nullif(trim(size), '')
where model is null
  and upper(trim(department)) <> 'DTF';

update public.inventory_items
set sku_code = 'SKU-' || upper(substr(replace(id::text, '-', ''), 1, 10))
where nullif(trim(sku_code), '') is null;

update public.inventory_items
set sku_name = concat_ws(
    ' ',
    nullif(trim(category), ''),
    nullif(trim(brand), ''),
    nullif(trim(material), ''),
    nullif(trim(color), ''),
    nullif(trim(coalesce(model, size)), '')
)
where nullif(trim(sku_name), '') is null;

create unique index if not exists inventory_items_sku_code_unique
on public.inventory_items (lower(trim(sku_code)))
where sku_code is not null;

create index if not exists inventory_items_master_data_idx
on public.inventory_items (
    department_id, category_id, brand_id, is_active
);

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'inventory_items_department_id_fkey'
    ) then
        alter table public.inventory_items
        add constraint inventory_items_department_id_fkey
        foreign key (department_id)
        references public.inventory_departments(id) on delete restrict;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'inventory_items_category_id_fkey'
    ) then
        alter table public.inventory_items
        add constraint inventory_items_category_id_fkey
        foreign key (category_id)
        references public.inventory_categories(id) on delete restrict;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'inventory_items_brand_id_fkey'
    ) then
        alter table public.inventory_items
        add constraint inventory_items_brand_id_fkey
        foreign key (brand_id)
        references public.inventory_brands(id) on delete restrict;
    end if;
end;
$$;

grant select, insert, update on public.inventory_departments
to anon, authenticated, service_role;

grant select, insert, update on public.inventory_categories
to anon, authenticated, service_role;

grant select, insert, update on public.inventory_brands
to anon, authenticated, service_role;

grant select, insert, update on public.inventory_materials
to anon, authenticated, service_role;

grant select, insert, update, delete on public.inventory_category_materials
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
