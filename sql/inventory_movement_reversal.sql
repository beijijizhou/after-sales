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
    source_movement public.inventory_movements;
    current_item public.inventory_items;
    reversal_batch_id uuid := gen_random_uuid();
    reversal_date date := (now() at time zone 'America/New_York')::date;
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
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
            batch_id, reversal_of_batch_id, created_by,
            unit_cost, 品牌, 材质, 成本
        ) values (
            source_movement.department, source_movement.category,
            source_movement.brand, source_movement.material,
            source_movement.color, source_movement.size,
            -source_movement.quantity_change, current_item.quantity,
            reversal_date,
            '撤销：' || coalesce(source_movement.reason, '库存变动'),
            reversal_batch_id, p_batch_id, effective_user,
            current_item.unit_cost, current_item.brand,
            current_item.material, current_item.unit_cost
        );
    end loop;

    return reversal_batch_id;
end;
$$;

grant execute on function public.reverse_inventory_movement_batch(uuid, text)
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
