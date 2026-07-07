alter table public.inventory_items
add column if not exists 材质 text;

alter table public.inventory_movements
add column if not exists 材质 text;

alter table public.inventory_sku_imports
add column if not exists 材质 text;

update public.inventory_items
set 材质 = '180g'
where 材质 is null;

update public.inventory_movements
set 材质 = '180g'
where 材质 is null;

update public.inventory_sku_imports
set 材质 = '180g'
where 材质 is null;

alter table public.inventory_items
alter column 材质 set default '180g';

alter table public.inventory_movements
alter column 材质 set default '180g';

alter table public.inventory_sku_imports
alter column 材质 set default '180g';

alter table public.inventory_items
alter column 材质 set not null;

alter table public.inventory_movements
alter column 材质 set not null;

alter table public.inventory_sku_imports
alter column 材质 set not null;

alter table public.inventory_items
drop constraint if exists inventory_items_category_color_size_key;

create unique index if not exists inventory_items_category_material_color_size_key
on public.inventory_items (category, 材质, color, size);

create or replace function public.adjust_inventory_stock(
    p_category text,
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
begin
    insert into public.inventory_items (category, 材质, color, size, quantity)
    values (p_category, coalesce(nullif(p_material, ''), '180g'), p_color, p_size, 0)
    on conflict (category, 材质, color, size) do nothing;

    select *
    into current_item
    from public.inventory_items
    where category = p_category
      and 材质 = coalesce(nullif(p_material, ''), '180g')
      and color = p_color
      and size = p_size
    for update;

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
        category,
        材质,
        color,
        size,
        quantity_change,
        quantity_after,
        movement_date,
        reason
    )
    values (
        p_category,
        current_item.材质,
        p_color,
        p_size,
        p_quantity_change,
        current_item.quantity,
        coalesce(p_movement_date, current_date),
        p_reason
    );

    return current_item;
end;
$$;

grant execute on function public.adjust_inventory_stock(text, text, text, text, integer, text, date) to anon;
grant execute on function public.adjust_inventory_stock(text, text, text, text, integer, text, date) to authenticated;
grant execute on function public.adjust_inventory_stock(text, text, text, text, integer, text, date) to service_role;

notify pgrst, 'reload schema';
