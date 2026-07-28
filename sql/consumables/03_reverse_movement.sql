begin;

create or replace function public.reverse_consumable_movement_batch(
    p_batch_id uuid,
    p_created_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    original_batch public.consumable_movement_batches;
    original_movement public.consumable_movements;
    selected_item public.consumable_items;
    reversal_batch_id uuid := gen_random_uuid();
begin
    select *
    into original_batch
    from public.consumable_movement_batches
    where id = p_batch_id
    for update;

    if original_batch.id is null then
        raise exception '找不到需要撤销的耗材记录';
    end if;

    if original_batch.movement_type = 'reversal' then
        raise exception '撤销记录不能再次撤销';
    end if;

    if exists (
        select 1
        from public.consumable_movement_batches
        where reversal_of_batch_id = p_batch_id
    ) then
        raise exception '该耗材批次已经撤销';
    end if;

    insert into public.consumable_movement_batches (
        id, department_id, movement_type, movement_date,
        total_quantity, note, created_by, reversal_of_batch_id
    ) values (
        reversal_batch_id,
        original_batch.department_id,
        'reversal',
        (now() at time zone 'America/New_York')::date,
        original_batch.total_quantity,
        '撤销批次 ' || original_batch.id::text,
        coalesce(nullif(trim(p_created_by), ''), 'system'),
        original_batch.id
    );

    for original_movement in
        select *
        from public.consumable_movements
        where batch_id = p_batch_id
        order by created_at desc, id
    loop
        select *
        into selected_item
        from public.consumable_items
        where id = original_movement.item_id
        for update;

        if selected_item.current_quantity - original_movement.quantity_change < 0 then
            raise exception '无法撤销：% 的剩余库存不足',
                selected_item.name;
        end if;

        update public.consumable_items
        set current_quantity =
                current_quantity - original_movement.quantity_change,
            updated_at = now()
        where id = selected_item.id
        returning * into selected_item;

        insert into public.consumable_movements (
            batch_id, item_id, movement_date, quantity_change,
            quantity_after, unit_cost, note, created_by,
            reversal_of_movement_id
        ) values (
            reversal_batch_id,
            selected_item.id,
            (now() at time zone 'America/New_York')::date,
            -original_movement.quantity_change,
            selected_item.current_quantity,
            original_movement.unit_cost,
            '撤销原流水 ' || original_movement.id::text,
            coalesce(nullif(trim(p_created_by), ''), 'system'),
            original_movement.id
        );
    end loop;

    return reversal_batch_id;
end;
$$;

grant execute on function public.reverse_consumable_movement_batch(uuid, text)
to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
