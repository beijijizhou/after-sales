create table if not exists public.inventory_sku_change_log (
    id uuid primary key default gen_random_uuid(),
    department text not null,
    old_identity jsonb not null,
    new_identity jsonb not null,
    affected_items integer not null default 0,
    affected_quantity integer not null default 0,
    changed_by text not null default 'system',
    changed_at timestamptz not null default now()
);

create index if not exists inventory_sku_change_log_changed_at_idx
on public.inventory_sku_change_log (changed_at desc);

create or replace function public.update_inventory_sku_identities(
    p_department text,
    p_changes jsonb,
    p_changed_by text default 'system'
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    change_row jsonb;
    source_item public.inventory_items%rowtype;
    target_item public.inventory_items%rowtype;
    old_category text;
    old_brand text;
    old_material text;
    old_color text;
    new_category text;
    new_brand text;
    new_material text;
    new_color text;
    item_count integer;
    quantity_count integer;
    updated_count integer := 0;
    merged_quantity integer;
    merged_cost numeric;
begin
    if jsonb_typeof(p_changes) <> 'array' then
        raise exception 'p_changes must be a JSON array';
    end if;

    for change_row in select value from jsonb_array_elements(p_changes)
    loop
        old_category := coalesce(change_row->>'old_category', '');
        old_brand := coalesce(change_row->>'old_brand', '');
        old_material := coalesce(change_row->>'old_material', '');
        old_color := coalesce(change_row->>'old_color', '');
        new_category := coalesce(change_row->>'new_category', '');
        new_brand := coalesce(change_row->>'new_brand', '');
        new_material := coalesce(change_row->>'new_material', '');
        new_color := coalesce(change_row->>'new_color', '');

        if new_material = '' or new_color = '' then
            raise exception '材质和颜色不能为空';
        end if;

        select count(*), coalesce(sum(quantity), 0)
        into item_count, quantity_count
        from public.inventory_items
        where department = p_department
          and coalesce(category, '') = old_category
          and coalesce(brand, '') = old_brand
          and coalesce(material, '') = old_material
          and coalesce(color, '') = old_color;

        if item_count = 0 then
            continue;
        end if;

        for source_item in
            select *
            from public.inventory_items
            where department = p_department
              and coalesce(category, '') = old_category
              and coalesce(brand, '') = old_brand
              and coalesce(material, '') = old_material
              and coalesce(color, '') = old_color
            for update
        loop
            select * into target_item
            from public.inventory_items
            where department = p_department
              and coalesce(category, '') = new_category
              and coalesce(brand, '') = new_brand
              and coalesce(material, '') = new_material
              and coalesce(color, '') = new_color
              and size = source_item.size
              and id <> source_item.id
            for update;

            if target_item.id is not null then
                merged_quantity := target_item.quantity + source_item.quantity;
                merged_cost := case
                    when merged_quantity > 0 then round((
                        target_item.unit_cost * target_item.quantity
                        + source_item.unit_cost * source_item.quantity
                    ) / merged_quantity, 2)
                    else coalesce(nullif(target_item.unit_cost, 0), source_item.unit_cost, 0)
                end;
                update public.inventory_items
                set quantity = merged_quantity,
                    unit_cost = merged_cost,
                    成本 = merged_cost,
                    updated_at = now()
                where id = target_item.id;

                update public.inventory_cost_lots
                set inventory_item_id = target_item.id
                where inventory_item_id = source_item.id;

                delete from public.inventory_items where id = source_item.id;
            else
                update public.inventory_items
                set category = nullif(new_category, ''),
                    brand = new_brand,
                    material = new_material,
                    color = new_color,
                    品牌 = new_brand,
                    材质 = new_material,
                    updated_at = now()
                where id = source_item.id;
            end if;
            target_item := null;
        end loop;

        update public.inventory_movements
        set category = nullif(new_category, ''), brand = new_brand,
            material = new_material, color = new_color,
            品牌 = new_brand, 材质 = new_material
        where department = p_department
          and coalesce(category, '') = old_category
          and coalesce(brand, '') = old_brand
          and coalesce(material, '') = old_material
          and coalesce(color, '') = old_color;

        update public.inventory_sku_imports
        set category = nullif(new_category, ''), brand = new_brand,
            material = new_material, color = new_color,
            品牌 = new_brand, 材质 = new_material
        where department = p_department
          and coalesce(category, '') = old_category
          and coalesce(brand, '') = old_brand
          and coalesce(material, '') = old_material
          and coalesce(color, '') = old_color;

        update public.inventory_snapshots
        set category = nullif(new_category, ''), brand = new_brand,
            material = new_material, color = new_color
        where department = p_department
          and coalesce(category, '') = old_category
          and coalesce(brand, '') = old_brand
          and coalesce(material, '') = old_material
          and coalesce(color, '') = old_color;

        update public.inventory_container_imports
        set category = nullif(new_category, ''), brand = new_brand,
            material = new_material, color = new_color,
            品牌 = new_brand, 材质 = new_material
        where department = p_department
          and coalesce(category, '') = old_category
          and coalesce(brand, '') = old_brand
          and coalesce(material, '') = old_material
          and coalesce(color, '') = old_color;

        insert into public.inventory_sku_change_log (
            department, old_identity, new_identity, affected_items,
            affected_quantity, changed_by
        ) values (
            p_department,
            jsonb_build_object(
                'category', old_category, 'brand', old_brand,
                'material', old_material, 'color', old_color
            ),
            jsonb_build_object(
                'category', new_category, 'brand', new_brand,
                'material', new_material, 'color', new_color
            ),
            item_count, quantity_count, coalesce(nullif(p_changed_by, ''), 'system')
        );
        updated_count := updated_count + 1;
    end loop;

    return updated_count;
end;
$$;

grant select on public.inventory_sku_change_log to anon, authenticated, service_role;
grant execute on function public.update_inventory_sku_identities(text, jsonb, text)
to anon, authenticated, service_role;

notify pgrst, 'reload schema';
