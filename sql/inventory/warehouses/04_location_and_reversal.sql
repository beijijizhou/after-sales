begin;

create or replace function public.set_inventory_warehouse_location(
    p_inventory_item_id uuid,
    p_warehouse_code text,
    p_location_note text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    balance_id uuid;
begin
    insert into public.inventory_warehouse_balances (
        inventory_item_id, warehouse_code, quantity, location_note
    ) values (
        p_inventory_item_id, trim(p_warehouse_code), 0,
        nullif(trim(p_location_note), '')
    )
    on conflict (inventory_item_id, warehouse_code) do update set
        location_note = excluded.location_note,
        updated_at = now()
    returning id into balance_id;
    return balance_id;
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
    update public.inventory_transfer_orders
    set status = 'reversed',
        received_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        received_at = now()
    where id = target_order.id;
    return target_order.id;
end;
$$;

grant execute on function public.set_inventory_warehouse_location(
    uuid, text, text
) to authenticated, service_role;
grant execute on function public.reverse_inventory_transfer(
    uuid, text
) to authenticated, service_role;

commit;
notify pgrst, 'reload schema';

