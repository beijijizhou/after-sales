begin;

create table if not exists public.inventory_warehouses (
    code text primary key,
    name text not null,
    purpose text,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

insert into public.inventory_warehouses (code, name, purpose, sort_order)
values
    ('25', '25仓', '主要衣服出库，也可存储', 1),
    ('60', '60仓', '主要存储', 2),
    ('70', '70仓', '主要存储', 3)
on conflict (code) do update set
    name = excluded.name,
    purpose = excluded.purpose,
    sort_order = excluded.sort_order,
    is_active = true;

create table if not exists public.inventory_warehouse_balances (
    id uuid primary key default gen_random_uuid(),
    inventory_item_id uuid not null
        references public.inventory_items(id) on delete restrict,
    warehouse_code text not null
        references public.inventory_warehouses(code) on delete restrict,
    quantity integer not null default 0 check (quantity >= 0),
    location_note text,
    updated_at timestamptz not null default now(),
    unique (inventory_item_id, warehouse_code)
);

create index if not exists inventory_warehouse_balances_warehouse_idx
on public.inventory_warehouse_balances (warehouse_code, inventory_item_id);

insert into public.inventory_warehouse_balances (
    inventory_item_id, warehouse_code, quantity
)
select id, '25', quantity
from public.inventory_items
on conflict (inventory_item_id, warehouse_code) do nothing;

alter table public.inventory_movements
add column if not exists warehouse_code text;

update public.inventory_movements
set warehouse_code = '25'
where warehouse_code is null or trim(warehouse_code) = '';

alter table public.inventory_movements
alter column warehouse_code set default '25';

alter table public.inventory_movements
alter column warehouse_code set not null;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'inventory_movements_warehouse_code_fkey'
    ) then
        alter table public.inventory_movements
        add constraint inventory_movements_warehouse_code_fkey
        foreign key (warehouse_code)
        references public.inventory_warehouses(code);
    end if;
end;
$$;

create or replace function public.adjust_inventory_warehouse_balance(
    p_inventory_item_id uuid,
    p_warehouse_code text,
    p_quantity_change integer,
    p_location_note text default null
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    resulting_quantity integer;
    normalized_warehouse text := trim(p_warehouse_code);
begin
    if p_quantity_change = 0 then
        select quantity into resulting_quantity
        from public.inventory_warehouse_balances
        where inventory_item_id = p_inventory_item_id
          and warehouse_code = normalized_warehouse;
        return coalesce(resulting_quantity, 0);
    end if;

    update public.inventory_warehouse_balances
    set quantity = quantity + p_quantity_change,
        location_note = coalesce(
            nullif(trim(p_location_note), ''), location_note
        ),
        updated_at = now()
    where inventory_item_id = p_inventory_item_id
      and warehouse_code = normalized_warehouse
      and quantity + p_quantity_change >= 0
    returning quantity into resulting_quantity;

    if resulting_quantity is not null then
        return resulting_quantity;
    end if;
    if p_quantity_change < 0 then
        raise exception '仓库 % 库存不足', normalized_warehouse;
    end if;

    insert into public.inventory_warehouse_balances (
        inventory_item_id, warehouse_code, quantity, location_note
    ) values (
        p_inventory_item_id, normalized_warehouse, p_quantity_change,
        nullif(trim(p_location_note), '')
    )
    returning quantity into resulting_quantity;
    return resulting_quantity;
end;
$$;

create or replace function public.sync_inventory_movement_to_warehouse()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    target_item_id uuid;
begin
    select id into target_item_id
    from public.inventory_items
    where department = new.department
      and coalesce(category, '') = coalesce(new.category, '')
      and coalesce(brand, '') = coalesce(new.brand, '')
      and coalesce(material, '') = coalesce(new.material, '')
      and coalesce(color, '') = coalesce(new.color, '')
      and coalesce(size, '') = coalesce(new.size, '')
    limit 1;

    if target_item_id is null then
        raise exception '仓库分布无法匹配库存 SKU';
    end if;
    perform public.adjust_inventory_warehouse_balance(
        target_item_id, coalesce(new.warehouse_code, '25'),
        new.quantity_change, null
    );
    return new;
end;
$$;

drop trigger if exists inventory_movement_warehouse_sync
on public.inventory_movements;

create trigger inventory_movement_warehouse_sync
after insert on public.inventory_movements
for each row execute function public.sync_inventory_movement_to_warehouse();

create table if not exists public.inventory_transfer_orders (
    id uuid primary key default gen_random_uuid(),
    transfer_number text not null unique,
    from_warehouse text references public.inventory_warehouses(code),
    to_warehouse text not null references public.inventory_warehouses(code),
    status text not null default 'pending'
        check (status in (
            'pending', 'in_transit', 'completed', 'cancelled', 'reversed'
        )),
    note text,
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    dispatched_by text,
    dispatched_at timestamptz,
    received_by text,
    received_at timestamptz
);

alter table public.inventory_transfer_orders
drop constraint if exists inventory_transfer_orders_status_check;
alter table public.inventory_transfer_orders
add constraint inventory_transfer_orders_status_check
check (status in (
    'pending', 'in_transit', 'completed', 'cancelled', 'reversed'
));

create table if not exists public.inventory_transfer_lines (
    id uuid primary key default gen_random_uuid(),
    transfer_order_id uuid not null
        references public.inventory_transfer_orders(id) on delete restrict,
    inventory_item_id uuid not null
        references public.inventory_items(id) on delete restrict,
    quantity_sent integer not null default 0 check (quantity_sent >= 0),
    quantity_received integer not null default 0 check (quantity_received >= 0),
    source_location text,
    target_location text,
    note text,
    unique (transfer_order_id, inventory_item_id)
);

create index if not exists inventory_transfer_orders_status_idx
on public.inventory_transfer_orders (status, created_at desc);

create index if not exists inventory_transfer_lines_order_idx
on public.inventory_transfer_lines (transfer_order_id);

grant select on public.inventory_warehouses,
    public.inventory_warehouse_balances,
    public.inventory_transfer_orders,
    public.inventory_transfer_lines
to authenticated, service_role;

grant insert, update on public.inventory_warehouse_balances,
    public.inventory_transfer_orders,
    public.inventory_transfer_lines
to authenticated, service_role;

commit;
notify pgrst, 'reload schema';

