begin;

create extension if not exists pgcrypto;

alter table public.inventory_movements
add column if not exists source_type text;

create table if not exists public.inventory_cost_lots (
    id uuid primary key default gen_random_uuid(),
    inventory_item_id uuid not null
        references public.inventory_items(id) on delete restrict,
    inbound_movement_id uuid
        references public.inventory_movements(id) on delete restrict,
    batch_id uuid,
    source_type text not null,
    received_quantity integer not null check (received_quantity > 0),
    remaining_quantity integer not null,
    unit_cost numeric(12, 4),
    movement_date date not null,
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    reversal_movement_id uuid
        references public.inventory_movements(id) on delete restrict,
    reversed_at timestamptz,
    constraint inventory_cost_lots_source_type_check
        check (source_type in ('opening', 'bulk', 'transfer')),
    constraint inventory_cost_lots_remaining_check
        check (
            remaining_quantity >= 0
            and remaining_quantity <= received_quantity
        ),
    constraint inventory_cost_lots_unit_cost_check
        check (unit_cost is null or unit_cost >= 0)
);

create table if not exists public.inventory_cost_allocations (
    id uuid primary key default gen_random_uuid(),
    outbound_movement_id uuid not null
        references public.inventory_movements(id) on delete restrict,
    cost_lot_id uuid not null
        references public.inventory_cost_lots(id) on delete restrict,
    quantity integer not null check (quantity > 0),
    unit_cost numeric(12, 4),
    source_type text not null,
    created_at timestamptz not null default now(),
    reversal_movement_id uuid
        references public.inventory_movements(id) on delete restrict,
    reversed_at timestamptz,
    constraint inventory_cost_allocations_source_type_check
        check (source_type in ('opening', 'bulk', 'transfer')),
    constraint inventory_cost_allocations_unit_cost_check
        check (unit_cost is null or unit_cost >= 0),
    unique (outbound_movement_id, cost_lot_id)
);

create index if not exists inventory_cost_lots_active_item_idx
on public.inventory_cost_lots (
    inventory_item_id, source_type, movement_date, created_at
)
where reversed_at is null and remaining_quantity > 0;

create index if not exists inventory_cost_lots_batch_idx
on public.inventory_cost_lots (batch_id);

create index if not exists inventory_cost_allocations_outbound_idx
on public.inventory_cost_allocations (outbound_movement_id)
where reversed_at is null;

create index if not exists inventory_cost_allocations_lot_idx
on public.inventory_cost_allocations (cost_lot_id);

-- Existing stock becomes one opening lot per SKU. A rerun only fills a
-- positive gap, so this migration is safe to execute more than once.
with active_balances as (
    select
        inventory_item_id,
        sum(remaining_quantity)::integer as remaining_quantity
    from public.inventory_cost_lots
    where reversed_at is null
    group by inventory_item_id
)
insert into public.inventory_cost_lots (
    inventory_item_id, source_type, received_quantity, remaining_quantity,
    unit_cost, movement_date, note, created_by
)
select
    item.id,
    'opening',
    item.quantity - coalesce(balance.remaining_quantity, 0),
    item.quantity - coalesce(balance.remaining_quantity, 0),
    nullif(item.unit_cost, 0),
    (now() at time zone 'America/New_York')::date,
    '成本批次功能启用时的期初库存',
    'system'
from public.inventory_items item
left join active_balances balance on balance.inventory_item_id = item.id
where item.quantity > coalesce(balance.remaining_quantity, 0);

grant select, insert, update on public.inventory_cost_lots
to anon, authenticated, service_role;

grant select, insert, update on public.inventory_cost_allocations
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
