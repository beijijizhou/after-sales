begin;

alter table public.inventory_transfer_orders
add column if not exists business_date date;

alter table public.inventory_transfer_orders
add column if not exists balance_effect_applied boolean not null default true;

alter table public.inventory_transfer_orders
add column if not exists balance_effect_note text;

update public.inventory_transfer_orders
set business_date = (created_at at time zone 'America/New_York')::date
where business_date is null;

alter table public.inventory_transfer_orders
alter column business_date set default
    ((now() at time zone 'America/New_York')::date);

alter table public.inventory_transfer_orders
alter column business_date set not null;

create index if not exists inventory_transfer_orders_business_date_idx
on public.inventory_transfer_orders (business_date desc, created_at desc);

create or replace function public.record_inventory_transfer_baseline(
    p_business_date date,
    p_from_warehouse text,
    p_to_warehouse text,
    p_lines jsonb,
    p_note text default null,
    p_operated_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    order_id uuid := gen_random_uuid();
    line_row jsonb;
    item_id uuid;
    moved_quantity integer;
    transfer_no text := 'TR-' ||
        to_char(coalesce(p_business_date, (now() at time zone 'America/New_York')::date), 'YYYYMMDD') || '-' ||
        upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6));
begin
    if trim(p_from_warehouse) = trim(p_to_warehouse) then
        raise exception '来源仓库和目标仓库不能相同';
    end if;

    insert into public.inventory_transfer_orders (
        id, transfer_number, business_date,
        from_warehouse, to_warehouse, status,
        note, created_by, dispatched_by, dispatched_at,
        received_by, received_at,
        balance_effect_applied, balance_effect_note
    ) values (
        order_id, transfer_no,
        coalesce(p_business_date, (now() at time zone 'America/New_York')::date),
        trim(p_from_warehouse), trim(p_to_warehouse), 'completed',
        nullif(trim(p_note), ''),
        coalesce(nullif(trim(p_operated_by), ''), 'system'),
        coalesce(nullif(trim(p_operated_by), ''), 'system'), now(),
        coalesce(nullif(trim(p_operated_by), ''), 'system'), now(),
        false, '期初仓库流程启用：当前仓库分布已包含本次结果，未重复调整库存'
    );

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        item_id := (line_row->>'inventory_item_id')::uuid;
        moved_quantity := coalesce((line_row->>'quantity')::integer, 0);
        if moved_quantity <= 0 then
            continue;
        end if;
        insert into public.inventory_transfer_lines (
            transfer_order_id, inventory_item_id,
            quantity_sent, quantity_received,
            source_location, target_location, note
        ) values (
            order_id, item_id, moved_quantity, moved_quantity,
            nullif(trim(line_row->>'source_location'), ''),
            nullif(trim(line_row->>'target_location'), ''),
            nullif(trim(line_row->>'note'), '')
        );
    end loop;

    if not exists (
        select 1 from public.inventory_transfer_lines
        where transfer_order_id = order_id
    ) then
        raise exception '实际调拨数量不能全部为 0';
    end if;
    return order_id;
end;
$$;

create or replace function public.reverse_inventory_transfer(
    p_order_id uuid,
    p_operated_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    target_order public.inventory_transfer_orders%rowtype;
    target_line public.inventory_transfer_lines%rowtype;
begin
    select * into target_order
    from public.inventory_transfer_orders
    where id = p_order_id for update;
    if target_order.id is null
       or target_order.status in ('cancelled', 'reversed') then
        raise exception '该调拨单不能撤销';
    end if;
    if target_order.status = 'pending' then
        update public.inventory_transfer_orders
        set status = 'cancelled',
            received_by = coalesce(
                nullif(trim(p_operated_by), ''), 'system'
            ),
            received_at = now()
        where id = target_order.id;
        return target_order.id;
    end if;

    if target_order.balance_effect_applied then
        for target_line in
            select * from public.inventory_transfer_lines
            where transfer_order_id = target_order.id
            for update
        loop
            if target_order.status = 'completed'
               and target_line.quantity_received > 0 then
                perform public.adjust_inventory_warehouse_balance(
                    target_line.inventory_item_id, target_order.to_warehouse,
                    -target_line.quantity_received, target_line.target_location
                );
            end if;
            if target_line.quantity_sent > 0 then
                perform public.adjust_inventory_warehouse_balance(
                    target_line.inventory_item_id, target_order.from_warehouse,
                    target_line.quantity_sent, target_line.source_location
                );
            end if;
        end loop;
    end if;

    update public.inventory_transfer_orders
    set status = 'reversed',
        received_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        received_at = now()
    where id = target_order.id;
    return target_order.id;
end;
$$;

grant execute on function public.record_inventory_transfer_baseline(
    date, text, text, jsonb, text, text
) to authenticated, service_role;

grant execute on function public.reverse_inventory_transfer(
    uuid, text
) to authenticated, service_role;

commit;
notify pgrst, 'reload schema';
