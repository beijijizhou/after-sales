begin;

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

insert into public.inventory_materials (name)
select distinct trim(item.material)
from public.inventory_items item
where nullif(trim(item.material), '') is not null
on conflict do nothing;

insert into public.inventory_category_materials (category_id, material_id)
select distinct item.category_id, material.id
from public.inventory_items item
join public.inventory_materials material
  on lower(trim(material.name)) = lower(trim(item.material))
where item.category_id is not null
  and nullif(trim(item.material), '') is not null
on conflict do nothing;

grant select, insert, update on public.inventory_materials
to anon, authenticated, service_role;

grant select, insert, update, delete on public.inventory_category_materials
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
