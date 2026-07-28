begin;

create or replace function public.apply_consumable_movement_batch(
    p_department_code text,
    p_movement_type text,
    p_movement_date date,
    p_rows jsonb,
    p_batch_id uuid default gen_random_uuid(),
    p_created_by text default 'system',
    p_note text default null,
    p_source_file_name text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    selected_department public.inventory_departments;
    selected_item public.consumable_items;
    movement_row jsonb;
    effective_batch_id uuid := coalesce(p_batch_id, gen_random_uuid());
    effective_type text := lower(trim(coalesce(p_movement_type, '')));
    supplied_quantity numeric(14, 4);
    quantity_change numeric(14, 4);
    supplied_unit_cost numeric(14, 4);
    batch_total numeric(14, 4) := 0;
begin
    if effective_type not in ('inbound', 'issue', 'adjustment') then
        raise exception '不支持的耗材操作类型：%', p_movement_type;
    end if;

    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
        raise exception '耗材出入库批次不能为空';
    end if;

    select *
    into selected_department
    from public.inventory_departments
    where lower(trim(code)) = lower(trim(p_department_code))
      and is_active
    limit 1;

    if selected_department.id is null then
        raise exception '未找到有效部门：%', p_department_code;
    end if;

    insert into public.consumable_movement_batches (
        id, department_id, movement_type, movement_date,
        note, source_file_name, created_by
    ) values (
        effective_batch_id,
        selected_department.id,
        effective_type,
        coalesce(
            p_movement_date,
            (now() at time zone 'America/New_York')::date
        ),
        nullif(trim(p_note), ''),
        nullif(trim(p_source_file_name), ''),
        coalesce(nullif(trim(p_created_by), ''), 'system')
    );

    for movement_row in select * from jsonb_array_elements(p_rows)
    loop
        supplied_quantity := (movement_row->>'quantity')::numeric(14, 4);

        if supplied_quantity is null or supplied_quantity = 0 then
            raise exception '耗材数量不能为 0';
        end if;

        if effective_type in ('inbound', 'issue') and supplied_quantity < 0 then
            raise exception '入库和领用数量请填写正数';
        end if;

        quantity_change := case effective_type
            when 'inbound' then abs(supplied_quantity)
            when 'issue' then -abs(supplied_quantity)
            else supplied_quantity
        end;

        supplied_unit_cost := case
            when nullif(movement_row->>'unit_cost', '') is null then null
            else (movement_row->>'unit_cost')::numeric(14, 4)
        end;

        select *
        into selected_item
        from public.consumable_items
        where id = (movement_row->>'item_id')::uuid
        for update;

        if selected_item.id is null then
            raise exception '耗材 SKU 不存在：%', movement_row->>'item_id';
        end if;

        if selected_item.department_id <> selected_department.id then
            raise exception '耗材 SKU 不属于所选部门：%', selected_item.name;
        end if;

        if not selected_item.is_active then
            raise exception '耗材 SKU 已停用：%', selected_item.name;
        end if;

        if selected_item.current_quantity + quantity_change < 0 then
            raise exception '耗材库存不足：% 当前 % %，本次领用 % %',
                selected_item.name,
                selected_item.current_quantity,
                selected_item.base_unit,
                abs(quantity_change),
                selected_item.base_unit;
        end if;

        update public.consumable_items
        set current_quantity = current_quantity + quantity_change,
            updated_at = now()
        where id = selected_item.id
        returning * into selected_item;

        insert into public.consumable_movements (
            batch_id, item_id, movement_date, quantity_change,
            quantity_after, unit_cost, note, created_by
        ) values (
            effective_batch_id,
            selected_item.id,
            coalesce(
                p_movement_date,
                (now() at time zone 'America/New_York')::date
            ),
            quantity_change,
            selected_item.current_quantity,
            supplied_unit_cost,
            nullif(trim(movement_row->>'note'), ''),
            coalesce(nullif(trim(p_created_by), ''), 'system')
        );

        batch_total := batch_total + abs(quantity_change);
    end loop;

    update public.consumable_movement_batches
    set total_quantity = batch_total
    where id = effective_batch_id;

    return effective_batch_id;
end;
$$;

grant execute on function public.apply_consumable_movement_batch(
    text, text, date, jsonb, uuid, text, text, text
) to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
