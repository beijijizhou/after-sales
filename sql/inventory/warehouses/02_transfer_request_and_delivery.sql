begin;

create or replace function public.create_inventory_transfer_request(
    p_from_warehouse text,
    p_to_warehouse text,
    p_lines jsonb,
    p_note text default null,
    p_created_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    order_id uuid := gen_random_uuid();
    line_row jsonb;
    transfer_no text := 'TR-' ||
        to_char(now() at time zone 'America/New_York', 'YYYYMMDD') || '-' ||
        upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6));
begin
    if jsonb_typeof(p_lines) <> 'array' or jsonb_array_length(p_lines) = 0 then
        raise exception '补货任务至少需要一个 SKU';
    end if;
    if nullif(trim(p_to_warehouse), '') is null then
        raise exception '目标仓库不能为空';
    end if;
    if nullif(trim(p_from_warehouse), '') = trim(p_to_warehouse) then
        raise exception '来源仓库和目标仓库不能相同';
    end if;

    insert into public.inventory_transfer_orders (
        id, transfer_number, from_warehouse, to_warehouse,
        note, created_by
    ) values (
        order_id, transfer_no, nullif(trim(p_from_warehouse), ''),
        trim(p_to_warehouse), nullif(trim(p_note), ''),
        coalesce(nullif(trim(p_created_by), ''), 'system')
    );

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        insert into public.inventory_transfer_lines (
            transfer_order_id, inventory_item_id, note
        ) values (
            order_id, (line_row->>'inventory_item_id')::uuid,
            nullif(trim(line_row->>'note'), '')
        );
    end loop;
    return order_id;
end;
$$;

create or replace function public.dispatch_inventory_transfer(
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
    sent_quantity integer;
    source_code text;
begin
    select * into target_order
    from public.inventory_transfer_orders
    where id = p_order_id for update;
    if target_order.id is null or target_order.status <> 'pending' then
        raise exception '只有待配货任务可以确认发出';
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
        sent_quantity := coalesce((line_row->>'quantity')::integer, 0);
        if target_line.id is null or sent_quantity < 0 then
            raise exception '调拨明细无效';
        end if;
        if sent_quantity > 0 then
            perform public.adjust_inventory_warehouse_balance(
                target_line.inventory_item_id, source_code, -sent_quantity,
                line_row->>'source_location'
            );
        end if;
        update public.inventory_transfer_lines
        set quantity_sent = sent_quantity,
            source_location = nullif(trim(line_row->>'source_location'), ''),
            target_location = nullif(trim(line_row->>'target_location'), '')
        where id = target_line.id;
    end loop;

    if not exists (
        select 1 from public.inventory_transfer_lines
        where transfer_order_id = target_order.id and quantity_sent > 0
    ) then
        raise exception '实际发出数量不能全部为 0';
    end if;
    update public.inventory_transfer_orders
    set from_warehouse = source_code, status = 'in_transit',
        dispatched_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        dispatched_at = now()
    where id = target_order.id;
    return target_order.id;
end;
$$;

create or replace function public.receive_inventory_transfer(
    p_order_id uuid,
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
    received_quantity integer;
begin
    select * into target_order
    from public.inventory_transfer_orders
    where id = p_order_id for update;
    if target_order.id is null or target_order.status <> 'in_transit' then
        raise exception '只有运输中的调拨单可以确认收到';
    end if;

    for line_row in select * from jsonb_array_elements(p_lines)
    loop
        select * into target_line
        from public.inventory_transfer_lines
        where id = (line_row->>'line_id')::uuid
          and transfer_order_id = target_order.id
        for update;
        received_quantity := coalesce((line_row->>'quantity')::integer, 0);
        if target_line.id is null
           or received_quantity < 0
           or received_quantity > target_line.quantity_sent then
            raise exception '实际收到数量不能超过实际发出数量';
        end if;
        if received_quantity > 0 then
            perform public.adjust_inventory_warehouse_balance(
                target_line.inventory_item_id, target_order.to_warehouse,
                received_quantity, coalesce(
                    line_row->>'target_location', target_line.target_location
                )
            );
        end if;
        update public.inventory_transfer_lines
        set quantity_received = received_quantity,
            target_location = coalesce(
                nullif(trim(line_row->>'target_location'), ''), target_location
            )
        where id = target_line.id;
    end loop;

    update public.inventory_transfer_orders
    set status = 'completed',
        received_by = coalesce(nullif(trim(p_operated_by), ''), 'system'),
        received_at = now()
    where id = target_order.id;
    return target_order.id;
end;
$$;

grant execute on function public.create_inventory_transfer_request(
    text, text, jsonb, text, text
) to authenticated, service_role;
grant execute on function public.dispatch_inventory_transfer(
    uuid, text, jsonb, text
) to authenticated, service_role;
grant execute on function public.receive_inventory_transfer(
    uuid, jsonb, text
) to authenticated, service_role;

commit;
notify pgrst, 'reload schema';

