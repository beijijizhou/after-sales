begin;

drop function if exists public.reverse_inventory_movement_batch(uuid);
drop function if exists public.reverse_inventory_movement_batch(uuid, text);

create or replace function public.reverse_inventory_movement_batch(
    p_batch_id uuid,
    p_created_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    source_movement public.inventory_movements%rowtype;
    current_item public.inventory_items%rowtype;
    source_lot public.inventory_cost_lots%rowtype;
    allocation public.inventory_cost_allocations%rowtype;
    reversal_batch_id uuid := gen_random_uuid();
    new_reversal_movement_id uuid;
    reversal_date date := (now() at time zone 'America/New_York')::date;
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
    quantity_needed integer;
    restored_quantity integer;
    allocated_quantity integer;
    linked_received integer;
    linked_remaining integer;
    latest_bulk_cost numeric;
begin
    if not exists (
        select 1 from public.inventory_movements where batch_id = p_batch_id
    ) then
        raise exception '找不到库存变动批次';
    end if;

    if exists (
        select 1 from public.inventory_movements
        where batch_id = p_batch_id and reversal_of_batch_id is not null
    ) then
        raise exception '撤销记录不能再次撤销';
    end if;

    if exists (
        select 1 from public.inventory_movement_reversals
        where original_batch_id = p_batch_id
    ) then
        raise exception '这笔库存变动已经撤销';
    end if;

    insert into public.inventory_movement_reversals (
        original_batch_id, reversal_batch_id, reversed_by
    ) values (
        p_batch_id, reversal_batch_id, effective_user
    );

    for source_movement in
        select * from public.inventory_movements
        where batch_id = p_batch_id
        order by created_at, id
    loop
        select * into current_item
        from public.inventory_items
        where department = source_movement.department
          and coalesce(category, '') = coalesce(source_movement.category, '')
          and brand = source_movement.brand
          and material = source_movement.material
          and coalesce(color, '') = coalesce(source_movement.color, '')
          and coalesce(size, '') = coalesce(source_movement.size, '')
        for update;

        if current_item.id is null then
            raise exception '找不到原库存 SKU：% % % %',
                source_movement.brand, source_movement.material,
                source_movement.color, source_movement.size;
        end if;

        if current_item.quantity - source_movement.quantity_change < 0 then
            raise exception '无法撤销，SKU 当前库存不足：% % % %',
                source_movement.brand, source_movement.material,
                source_movement.color, source_movement.size;
        end if;

        update public.inventory_items
        set quantity = quantity - source_movement.quantity_change,
            updated_at = now()
        where id = current_item.id
        returning * into current_item;

        insert into public.inventory_movements (
            department, category, brand, material, color, size,
            quantity_change, quantity_after, movement_date, reason,
            batch_id, reversal_of_batch_id, created_by, source_type,
            unit_cost, 品牌, 材质, 成本
        ) values (
            source_movement.department, source_movement.category,
            source_movement.brand, source_movement.material,
            source_movement.color, source_movement.size,
            -source_movement.quantity_change, current_item.quantity,
            reversal_date,
            '撤销：' || coalesce(source_movement.reason, '库存变动'),
            reversal_batch_id, p_batch_id, effective_user, null,
            current_item.unit_cost, current_item.brand,
            current_item.material, current_item.unit_cost
        ) returning id into new_reversal_movement_id;

        if source_movement.quantity_change < 0 then
            restored_quantity := 0;
            for allocation in
                select *
                from public.inventory_cost_allocations
                where outbound_movement_id = source_movement.id
                  and reversed_at is null
                order by created_at, id
                for update
            loop
                update public.inventory_cost_lots
                set remaining_quantity = remaining_quantity + allocation.quantity
                where id = allocation.cost_lot_id
                  and reversed_at is null;

                if not found then
                    raise exception '无法恢复已撤销的成本批次';
                end if;

                update public.inventory_cost_allocations
                set reversal_movement_id = new_reversal_movement_id,
                    reversed_at = now()
                where id = allocation.id;
                restored_quantity := restored_quantity + allocation.quantity;
            end loop;

            quantity_needed := abs(source_movement.quantity_change) - restored_quantity;
            if quantity_needed > 0 then
                insert into public.inventory_cost_lots (
                    inventory_item_id, inbound_movement_id, batch_id,
                    source_type, received_quantity, remaining_quantity,
                    unit_cost, movement_date, note, created_by
                ) values (
                    current_item.id, new_reversal_movement_id, reversal_batch_id,
                    'opening', quantity_needed, quantity_needed,
                    nullif(source_movement.unit_cost, 0), reversal_date,
                    '恢复旧出库记录', effective_user
                );
            end if;
        else
            select
                coalesce(sum(received_quantity), 0)::integer,
                coalesce(sum(remaining_quantity), 0)::integer
            into linked_received, linked_remaining
            from public.inventory_cost_lots
            where inbound_movement_id = source_movement.id
              and reversed_at is null;

            if linked_received > 0 then
                if linked_received <> source_movement.quantity_change
                   or linked_remaining <> linked_received then
                    raise exception '无法撤销：这批入库已有部分库存被消耗';
                end if;

                update public.inventory_cost_lots
                set remaining_quantity = 0,
                    reversal_movement_id = new_reversal_movement_id,
                    reversed_at = now()
                where inbound_movement_id = source_movement.id
                  and reversed_at is null;
            else
                -- Legacy inbound movements have no linked lot. Remove their
                -- quantity from opening stock first, without consuming newer
                -- temporary-transfer lots unless no other stock remains.
                quantity_needed := source_movement.quantity_change;
                for source_lot in
                    select *
                    from public.inventory_cost_lots
                    where inventory_item_id = current_item.id
                      and reversed_at is null
                      and remaining_quantity > 0
                    order by
                        case source_type
                            when 'opening' then 0
                            when 'bulk' then 1
                            else 2
                        end,
                        movement_date,
                        created_at,
                        id
                    for update
                loop
                    exit when quantity_needed = 0;
                    allocated_quantity := least(
                        quantity_needed, source_lot.remaining_quantity
                    );
                    insert into public.inventory_cost_allocations (
                        outbound_movement_id, cost_lot_id, quantity,
                        unit_cost, source_type
                    ) values (
                        new_reversal_movement_id, source_lot.id,
                        allocated_quantity, source_lot.unit_cost,
                        source_lot.source_type
                    );
                    update public.inventory_cost_lots
                    set remaining_quantity = remaining_quantity - allocated_quantity
                    where id = source_lot.id;
                    quantity_needed := quantity_needed - allocated_quantity;
                end loop;

                if quantity_needed > 0 then
                    raise exception '无法撤销：成本批次库存不足，缺少 % 件',
                        quantity_needed;
                end if;
            end if;

            if source_movement.source_type = 'bulk' then
                select unit_cost into latest_bulk_cost
                from public.inventory_cost_lots
                where inventory_item_id = current_item.id
                  and source_type in ('bulk', 'opening')
                  and reversed_at is null
                  and remaining_quantity > 0
                  and unit_cost is not null
                order by movement_date desc, created_at desc
                limit 1;

                update public.inventory_items
                set unit_cost = coalesce(latest_bulk_cost, 0),
                    成本 = coalesce(latest_bulk_cost, 0)
                where id = current_item.id;
            end if;
        end if;
    end loop;

    return reversal_batch_id;
end;
$$;

grant execute on function public.reverse_inventory_movement_batch(uuid, text)
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
