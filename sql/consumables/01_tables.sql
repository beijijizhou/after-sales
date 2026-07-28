begin;

create extension if not exists pgcrypto;

create table if not exists public.consumable_items (
    id uuid primary key default gen_random_uuid(),
    department_id uuid not null
        references public.inventory_departments(id) on delete restrict,
    category text not null,
    name text not null,
    specification text not null default '',
    brand text not null default '',
    base_unit text not null,
    package_unit text,
    units_per_package numeric(14, 4),
    current_quantity numeric(14, 4) not null default 0,
    minimum_quantity numeric(14, 4),
    is_active boolean not null default true,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint consumable_items_category_required
        check (trim(category) <> ''),
    constraint consumable_items_name_required
        check (trim(name) <> ''),
    constraint consumable_items_base_unit_required
        check (trim(base_unit) <> ''),
    constraint consumable_items_quantity_nonnegative
        check (current_quantity >= 0),
    constraint consumable_items_minimum_nonnegative
        check (minimum_quantity is null or minimum_quantity >= 0),
    constraint consumable_items_package_quantity_positive
        check (units_per_package is null or units_per_package > 0),
    constraint consumable_items_package_pair
        check (
            (nullif(trim(coalesce(package_unit, '')), '') is null
                and units_per_package is null)
            or
            (nullif(trim(coalesce(package_unit, '')), '') is not null
                and units_per_package is not null)
        )
);

create unique index if not exists consumable_items_identity_unique
on public.consumable_items (
    department_id,
    lower(trim(category)),
    lower(trim(name)),
    lower(trim(specification)),
    lower(trim(brand)),
    lower(trim(base_unit))
);

create index if not exists consumable_items_filter_idx
on public.consumable_items (department_id, category, is_active);

create table if not exists public.consumable_movement_batches (
    id uuid primary key default gen_random_uuid(),
    department_id uuid not null
        references public.inventory_departments(id) on delete restrict,
    movement_type text not null,
    movement_date date not null,
    total_quantity numeric(14, 4) not null default 0,
    note text,
    source_file_name text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    reversal_of_batch_id uuid
        references public.consumable_movement_batches(id) on delete restrict,
    constraint consumable_batches_type_check
        check (movement_type in ('inbound', 'issue', 'adjustment', 'reversal')),
    constraint consumable_batches_total_nonnegative
        check (total_quantity >= 0)
);

create unique index if not exists consumable_batches_one_reversal
on public.consumable_movement_batches (reversal_of_batch_id)
where reversal_of_batch_id is not null;

create index if not exists consumable_batches_history_idx
on public.consumable_movement_batches (
    movement_date desc,
    department_id,
    movement_type
);

create table if not exists public.consumable_movements (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null
        references public.consumable_movement_batches(id) on delete restrict,
    item_id uuid not null
        references public.consumable_items(id) on delete restrict,
    movement_date date not null,
    quantity_change numeric(14, 4) not null,
    quantity_after numeric(14, 4) not null,
    unit_cost numeric(14, 4),
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    reversal_of_movement_id uuid
        references public.consumable_movements(id) on delete restrict,
    constraint consumable_movements_change_nonzero
        check (quantity_change <> 0),
    constraint consumable_movements_balance_nonnegative
        check (quantity_after >= 0),
    constraint consumable_movements_cost_nonnegative
        check (unit_cost is null or unit_cost >= 0)
);

create unique index if not exists consumable_movements_one_reversal
on public.consumable_movements (reversal_of_movement_id)
where reversal_of_movement_id is not null;

create index if not exists consumable_movements_item_history_idx
on public.consumable_movements (item_id, movement_date desc, created_at desc);

create index if not exists consumable_movements_batch_idx
on public.consumable_movements (batch_id);

grant select, insert, update on public.consumable_items
to anon, authenticated, service_role;

grant select on public.consumable_movement_batches
to anon, authenticated, service_role;

grant select on public.consumable_movements
to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
