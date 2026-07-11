alter table public.inventory_items
add column if not exists unit_cost numeric(10, 2) not null default 0;

alter table public.inventory_items
add column if not exists 成本 numeric(10, 2) not null default 0;

alter table public.inventory_movements
add column if not exists unit_cost numeric(10, 2) not null default 0;

alter table public.inventory_movements
add column if not exists 成本 numeric(10, 2) not null default 0;

create or replace function public.adjust_inventory_stock(
    p_department text,
    p_category text,
    p_brand text,
    p_material text,
    p_color text,
    p_size text,
    p_quantity_change integer,
    p_reason text default null,
    p_movement_date date default current_date
)
returns public.inventory_items
language plpgsql
security definer
set search_path = public
as $$
declare
    current_item public.inventory_items;
    normalized_department text := coalesce(nullif(trim(p_department), ''), 'DTF');
    normalized_category text := nullif(trim(coalesce(p_category, '')), '');
    normalized_brand text := coalesce(trim(p_brand), '');
    normalized_material text := coalesce(trim(p_material), '');
    normalized_color text := coalesce(trim(p_color), '');
    normalized_size text := coalesce(trim(p_size), '');
begin
    select *
    into current_item
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
            department,
            category,
            brand,
            material,
            color,
            size,
            unit_cost,
            quantity,
            品牌,
            材质,
            成本
        )
        values (
            normalized_department,
            normalized_category,
            normalized_brand,
            normalized_material,
            normalized_color,
            normalized_size,
            0,
            0,
            normalized_brand,
            normalized_material,
            0
        )
        returning * into current_item;
    end if;

    if current_item.quantity + p_quantity_change < 0 then
        raise exception '库存不足：当前库存 %, 调整数量 %',
            current_item.quantity,
            p_quantity_change;
    end if;

    update public.inventory_items
    set quantity = quantity + p_quantity_change,
        updated_at = now()
    where id = current_item.id
    returning * into current_item;

    insert into public.inventory_movements (
        department,
        category,
        brand,
        material,
        color,
        size,
        quantity_change,
        quantity_after,
        movement_date,
        reason,
        品牌,
        材质
    )
    values (
        normalized_department,
        normalized_category,
        normalized_brand,
        normalized_material,
        normalized_color,
        normalized_size,
        p_quantity_change,
        current_item.quantity,
        coalesce(p_movement_date, current_date),
        p_reason,
        normalized_brand,
        normalized_material
    );

    return current_item;
end;
$$;

grant execute on function public.adjust_inventory_stock(text, text, text, text, text, text, integer, text, date) to anon;
grant execute on function public.adjust_inventory_stock(text, text, text, text, text, text, integer, text, date) to authenticated;
grant execute on function public.adjust_inventory_stock(text, text, text, text, text, text, integer, text, date) to service_role;

create or replace function public.adjust_inventory_stock_with_cost(
    p_department text,
    p_category text,
    p_brand text,
    p_material text,
    p_color text,
    p_size text,
    p_quantity_change integer,
    p_reason text default null,
    p_movement_date date default current_date,
    p_unit_cost numeric default null
)
returns public.inventory_items
language plpgsql
security definer
set search_path = public
as $$
declare
    current_item public.inventory_items;
    normalized_department text := coalesce(nullif(trim(p_department), ''), 'DTF');
    normalized_category text := nullif(trim(coalesce(p_category, '')), '');
    normalized_brand text := coalesce(trim(p_brand), '');
    normalized_material text := coalesce(trim(p_material), '');
    normalized_color text := coalesce(trim(p_color), '');
    normalized_size text := coalesce(trim(p_size), '');
    normalized_unit_cost numeric := coalesce(p_unit_cost, 0);
begin
    select *
    into current_item
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
            department,
            category,
            brand,
            material,
            color,
            size,
            unit_cost,
            quantity,
            品牌,
            材质,
            成本
        )
        values (
            normalized_department,
            normalized_category,
            normalized_brand,
            normalized_material,
            normalized_color,
            normalized_size,
            normalized_unit_cost,
            0,
            normalized_brand,
            normalized_material,
            normalized_unit_cost
        )
        returning * into current_item;
    end if;

    if current_item.quantity + p_quantity_change < 0 then
        raise exception '库存不足：当前库存 %, 调整数量 %',
            current_item.quantity,
            p_quantity_change;
    end if;

    update public.inventory_items
    set quantity = quantity + p_quantity_change,
        unit_cost = normalized_unit_cost,
        成本 = normalized_unit_cost,
        updated_at = now()
    where id = current_item.id
    returning * into current_item;

    insert into public.inventory_movements (
        department,
        category,
        brand,
        material,
        color,
        size,
        quantity_change,
        quantity_after,
        movement_date,
        reason,
        unit_cost,
        品牌,
        材质,
        成本
    )
    values (
        normalized_department,
        normalized_category,
        normalized_brand,
        normalized_material,
        normalized_color,
        normalized_size,
        p_quantity_change,
        current_item.quantity,
        coalesce(p_movement_date, current_date),
        p_reason,
        normalized_unit_cost,
        normalized_brand,
        normalized_material,
        normalized_unit_cost
    );

    return current_item;
end;
$$;

grant execute on function public.adjust_inventory_stock_with_cost(text, text, text, text, text, text, integer, text, date, numeric) to anon;
grant execute on function public.adjust_inventory_stock_with_cost(text, text, text, text, text, text, integer, text, date, numeric) to authenticated;
grant execute on function public.adjust_inventory_stock_with_cost(text, text, text, text, text, text, integer, text, date, numeric) to service_role;

notify pgrst, 'reload schema';
