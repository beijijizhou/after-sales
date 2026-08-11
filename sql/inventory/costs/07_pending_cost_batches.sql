begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_pending_cost_batches (
    id uuid primary key default gen_random_uuid(),
    business_date date not null,
    department text not null,
    category text,
    brand text,
    material text not null,
    color text,
    size text,
    quantity integer not null check (quantity > 0),
    unit_cost numeric(14, 4),
    source_type text not null default 'bulk',
    inventory_effect text not null default 'already_in_inventory',
    status text not null default 'pending_review',
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint inventory_pending_cost_batches_unit_cost_check
        check (unit_cost is null or unit_cost > 0),
    constraint inventory_pending_cost_batches_source_type_check
        check (source_type in ('opening', 'bulk', 'transfer')),
    constraint inventory_pending_cost_batches_effect_check
        check (inventory_effect in ('already_in_inventory', 'not_posted')),
    constraint inventory_pending_cost_batches_status_check
        check (status in ('pending_review', 'ready_to_allocate', 'allocated', 'cancelled'))
);

create index if not exists inventory_pending_cost_batches_status_date_idx
on public.inventory_pending_cost_batches (status, business_date desc, created_at desc);

grant select, insert, update on public.inventory_pending_cost_batches
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
