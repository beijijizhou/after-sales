begin;

-- Prerequisite: 01_warehouse_schema_and_sync.sql and
-- ../schema/inventory_hoodie_style.sql are installed.
--
-- The movement-to-warehouse trigger matched a SKU without its style, so
-- hoodie movements for one style could change the warehouse balance of a
-- sibling style with the same material/color/size. Match the complete SKU
-- identity, including style. Non-hoodie SKUs store an empty style on both
-- sides and are unaffected.
create or replace function public.sync_inventory_movement_to_warehouse()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    target_item_id uuid;
begin
    select id into target_item_id
    from public.inventory_items
    where department = new.department
      and coalesce(category, '') = coalesce(new.category, '')
      and coalesce(brand, '') = coalesce(new.brand, '')
      and coalesce(material, '') = coalesce(new.material, '')
      and coalesce(style, '') = coalesce(new.style, '')
      and coalesce(color, '') = coalesce(new.color, '')
      and coalesce(size, '') = coalesce(new.size, '')
    limit 1;

    if target_item_id is null then
        raise exception '仓库分布无法匹配库存 SKU';
    end if;
    perform public.adjust_inventory_warehouse_balance(
        target_item_id, coalesce(new.warehouse_code, '25'),
        new.quantity_change, null
    );
    return new;
end;
$$;

commit;
notify pgrst, 'reload schema';
