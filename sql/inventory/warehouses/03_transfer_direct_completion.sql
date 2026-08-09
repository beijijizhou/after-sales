begin;

create or replace function public.complete_inventory_transfer_direct(
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
        to_char(now() at time zone 'America/New_York', 'YYYYMMDD') || '-' ||
        upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6));
begin
    if trim(p_from_warehouse) = trim(p_to_warehouse) then
        raise exception '来源仓库和目标仓库不能相同';
    end if;
    insert into public.inventory_transfer_orders (
        id, transfer_number, from_warehouse, to_warehouse, status,
        note, created_by, dispatched_by, dispatched_at,
        received_by, received_at
    ) values (
        order_id, transfer_no, trim(p_from_warehouse), trim(p_to_warehouse),
        'completed', nullif(trim(p_note), ''),
        coalesce(nullif(trim(p_operated_by), ''), 'system'),
        coalesce(nullif(trim(p_operated_by), ''), 'system'), now(),
        coalesce(nullif(trim(p_operated_by), ''), 'system'), now()
    );

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        item_id := (line_row->>'inventory_item_id')::uuid;
        moved_quantity := coalesce((line_row->>'quantity')::integer, 0);
        if moved_quantity <= 0 then
            continue;
        end if;
        perform public.adjust_inventory_warehouse_balance(
            item_id, trim(p_from_warehouse), -moved_quantity,
            line_row->>'source_location'
        );
        perform public.adjust_inventory_warehouse_balance(
            item_id, trim(p_to_warehouse), moved_quantity,
            line_row->>'target_location'
        );
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

create or replace function public.complete_pending_inventory_transfer(
    p_order_id uuid,
    p_from_warehouse text,
    p_lines jsonb,
    p_operated_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    target_order public.inventory_transfer_orders%rowtype;
    line_row jsonb;
    target_line public.inventory_transfer_lines%rowtype;
    moved_quantity integer;
    source_code text;
begin
    select * into target_order
    from public.inventory_transfer_orders
    where id = p_order_id for update;
    if target_order.id is null or target_order.status <> 'pending' then
        raise exception '只有待配货任务可以直接完成';
    end if;
    source_code := coalesce(
        nullif(trim(p_from_warehouse), ''), target_order.from_warehouse
    );
    if source_code is null or source_code = target_order.to_warehouse then
        raise exception '请选择有效来源仓库';
    end if;

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        select * into target_line
        from public.inventory_transfer_lines
        where id = (line_row->>'line_id')::uuid
          and transfer_order_id = target_order.id
        for update;
        moved_quantity := coalesce((line_row->>'quantity')::integer, 0);
        if target_line.id is null or moved_quantity < 0 then
            raise exception '调拨明细无效';
        end if;
        if moved_quantity > 0 then
            perform public.adjust_inventory_warehouse_balance(
                target_line.inventory_item_id, source_code, -moved_quantity,
                line_row->>'source_location'
            );
            perform public.adjust_inventory_warehouse_balance(
                target_line.inventory_item_id, target_order.to_warehouse,
                moved_quantity, line_row->>'target_location'
            );
        end if;
        update public.inventory_transfer_lines
        set quantity_sent = moved_quantity,
            quantity_received = moved_quantity,
            source_location = nullif(trim(line_row->>'source_location'), ''),
            target_location = nullif(trim(line_row->>'target_location'), '')
        where id = target_line.id;
    end loop;

    if not exists (
        select 1 from public.inventory_transfer_lines
        where transfer_order_id = target_order.id and quantity_sent > 0
    ) then
        raise exception '实际调拨数量不能全部为 0';
    end if;
    update public.inventory_transfer_orders
    set from_warehouse = source_code, status = 'completed',
        dispatched_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        dispatched_at = now(),
        received_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        received_at = now()
    where id = target_order.id;
    return target_order.id;
end;
$$;

grant execute on function public.complete_inventory_transfer_direct(
    text, text, jsonb, text, text
) to authenticated, service_role;
grant execute on function public.complete_pending_inventory_transfer(
    uuid, text, jsonb, text
) to authenticated, service_role;

commit;
notify pgrst, 'reload schema';

