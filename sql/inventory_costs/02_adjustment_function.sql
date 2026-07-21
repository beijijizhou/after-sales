begin;

drop function if exists public.apply_inventory_adjustment_batch(
    text, text, jsonb, uuid, text
);
drop function if exists public.apply_inventory_adjustment_batch(
    text, text, jsonb, uuid, text, text
);

create or replace function public.apply_inventory_adjustment_batch(
    p_department text,
    p_category text,
    p_rows jsonb,
    p_batch_id uuid default gen_random_uuid(),
    p_created_by text default 'system',
    p_source_type text default 'bulk'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    adjustment_row jsonb;
    current_item public.inventory_items;
    cost_lot public.inventory_cost_lots%rowtype;
    effective_batch_id uuid := coalesce(p_batch_id, gen_random_uuid());
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
    normalized_department text := coalesce(nullif(trim(p_department), ''), 'DTF');
    normalized_category text := nullif(trim(coalesce(p_category, '')), '');
    normalized_brand text;
    normalized_material text;
    normalized_color text;
    normalized_size text;
    effective_source_type text;
    quantity_change integer;
    movement_date date;
    has_unit_cost boolean;
    supplied_unit_cost numeric;
    lot_unit_cost numeric;
    lot_balance integer;
    quantity_needed integer;
    allocated_quantity integer;
    movement_id uuid;
begin
    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
        raise exception '库存调整批次不能为空';
    end if;

    for adjustment_row in select * from jsonb_array_elements(p_rows)
    loop
        normalized_brand := coalesce(trim(adjustment_row->>'brand'), '');
        normalized_material := coalesce(trim(adjustment_row->>'material'), '');
        normalized_color := coalesce(trim(adjustment_row->>'color'), '');
        normalized_size := upper(coalesce(trim(adjustment_row->>'size'), ''));
        quantity_change := (adjustment_row->>'quantity_change')::integer;
        movement_date := coalesce(
            (adjustment_row->>'movement_date')::date,
            (now() at time zone 'America/New_York')::date
        );
        has_unit_cost := adjustment_row ? 'unit_cost'
            and nullif(adjustment_row->>'unit_cost', '') is not null;
        supplied_unit_cost := case
            when has_unit_cost then (adjustment_row->>'unit_cost')::numeric
            else null
        end;
        effective_source_type := lower(coalesce(
            nullif(trim(adjustment_row->>'source_type'), ''),
            nullif(trim(p_source_type), ''),
            'bulk'
        ));

        if quantity_change = 0 then
            continue;
        end if;
        if supplied_unit_cost is not null and supplied_unit_cost < 0 then
            raise exception '库存成本不能小于 0';
        end if;
        if quantity_change > 0
           and effective_source_type not in ('opening', 'bulk', 'transfer') then
            raise exception '无法识别库存来源：%', effective_source_type;
        end if;

        select * into current_item
        from public.inventory_items
        where department = normalized_department
          and coalesce(category, '') = coalesce(normalized_category, '')
          and brand = normalized_brand
          and material = normalized_material
          and coalesce(color, '') = normalized_color
          and coalesce(size, '') = normalized_size
        for update;

        if current_item.id is null then
            insert into public.inventory_items (
                department, category, brand, material, color, size,
                unit_cost, quantity, 品牌, 材质, 成本
            ) values (
                normalized_department, normalized_category, normalized_brand,
                normalized_material, normalized_color, normalized_size,
                coalesce(supplied_unit_cost, 0), 0,
                normalized_brand, normalized_material,
                coalesce(supplied_unit_cost, 0)
            ) returning * into current_item;
        end if;

        select coalesce(sum(remaining_quantity), 0)::integer
        into lot_balance
        from public.inventory_cost_lots
        where inventory_item_id = current_item.id
          and reversed_at is null;

        if lot_balance < current_item.quantity then
            insert into public.inventory_cost_lots (
                inventory_item_id, source_type, received_quantity,
                remaining_quantity, unit_cost, movement_date, note, created_by
            ) values (
                current_item.id, 'opening', current_item.quantity - lot_balance,
                current_item.quantity - lot_balance,
                nullif(current_item.unit_cost, 0), movement_date,
                '自动补齐旧库存成本批次', effective_user
            );
        elsif lot_balance > current_item.quantity then
            raise exception '成本批次数量大于当前库存，请先检查 SKU：% % % %',
                normalized_brand, normalized_material, normalized_color,
                normalized_size;
        end if;

        if current_item.quantity + quantity_change < 0 then
            raise exception '库存不足：% % % %，当前库存 %，调整 %',
                normalized_brand, normalized_material, normalized_color,
                normalized_size, current_item.quantity, quantity_change;
        end if;

        update public.inventory_items
        set quantity = quantity + quantity_change,
            unit_cost = case
                when quantity_change > 0
                 and effective_source_type = 'bulk'
                 and supplied_unit_cost is not null
                    then supplied_unit_cost
                else unit_cost
            end,
            成本 = case
                when quantity_change > 0
                 and effective_source_type = 'bulk'
                 and supplied_unit_cost is not null
                    then supplied_unit_cost
                else 成本
            end,
            updated_at = now()
        where id = current_item.id
        returning * into current_item;

        insert into public.inventory_movements (
            department, category, brand, material, color, size,
            quantity_change, quantity_after, movement_date, reason,
            batch_id, created_by, source_type, unit_cost, 品牌, 材质, 成本
        ) values (
            normalized_department, normalized_category, normalized_brand,
            normalized_material, normalized_color, normalized_size,
            quantity_change, current_item.quantity, movement_date,
            adjustment_row->>'reason', effective_batch_id, effective_user,
            case when quantity_change > 0 then effective_source_type else null end,
            current_item.unit_cost, normalized_brand, normalized_material,
            current_item.unit_cost
        ) returning id into movement_id;

        if quantity_change > 0 then
            lot_unit_cost := supplied_unit_cost;
            insert into public.inventory_cost_lots (
                inventory_item_id, inbound_movement_id, batch_id, source_type,
                received_quantity, remaining_quantity, unit_cost,
                movement_date, note, created_by
            ) values (
                current_item.id, movement_id, effective_batch_id,
                effective_source_type, quantity_change, quantity_change,
                lot_unit_cost, movement_date, adjustment_row->>'reason',
                effective_user
            );
            continue;
        end if;

        quantity_needed := abs(quantity_change);
        for cost_lot in
            select *
            from public.inventory_cost_lots
            where inventory_item_id = current_item.id
              and reversed_at is null
              and remaining_quantity > 0
            order by
                case when source_type = 'transfer' then 0 else 1 end,
                movement_date,
                created_at,
                id
            for update
        loop
            exit when quantity_needed = 0;
            allocated_quantity := least(
                quantity_needed, cost_lot.remaining_quantity
            );
            insert into public.inventory_cost_allocations (
                outbound_movement_id, cost_lot_id, quantity,
                unit_cost, source_type
            ) values (
                movement_id, cost_lot.id, allocated_quantity,
                cost_lot.unit_cost, cost_lot.source_type
            );
            update public.inventory_cost_lots
            set remaining_quantity = remaining_quantity - allocated_quantity
            where id = cost_lot.id;
            quantity_needed := quantity_needed - allocated_quantity;
        end loop;

        if quantity_needed > 0 then
            raise exception '成本批次库存不足：% % % %，缺少 % 件',
                normalized_brand, normalized_material, normalized_color,
                normalized_size, quantity_needed;
        end if;
    end loop;

    return effective_batch_id;
end;
$$;

grant execute on function public.apply_inventory_adjustment_batch(
    text, text, jsonb, uuid, text, text
) to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
