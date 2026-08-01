begin;

-- Merge into an existing SK/180g SKU when one already exists; otherwise
-- relabel the current SK/160g row without changing its quantity.
do $$
declare
    source_row record;
    target_id uuid;
begin
    for source_row in
        select *
        from public.inventory_items
        where department = 'DTF'
          and coalesce(nullif(brand, ''), nullif(品牌, '')) = 'SK'
          and coalesce(nullif(material, ''), nullif(材质, '')) = '160g'
    loop
        target_id := null;
        select target.id
        into target_id
        from public.inventory_items target
        where target.id <> source_row.id
          and target.department = source_row.department
          and coalesce(target.category, '') = coalesce(source_row.category, '')
          and coalesce(nullif(target.brand, ''), nullif(target.品牌, '')) = 'SK'
          and coalesce(nullif(target.material, ''), nullif(target.材质, '')) = '180g'
          and coalesce(target.color, '') = coalesce(source_row.color, '')
          and coalesce(target.size, '') = coalesce(source_row.size, '')
        limit 1;

        if target_id is null then
            update public.inventory_items
            set brand = 'SK',
                品牌 = 'SK',
                material = '180g',
                材质 = '180g',
                updated_at = now()
            where id = source_row.id;
        else
            update public.inventory_items target
            set quantity = target.quantity + source_row.quantity,
                unit_cost = case
                    when target.unit_cost = 0 then source_row.unit_cost
                    else target.unit_cost
                end,
                成本 = case
                    when target.成本 = 0 then source_row.成本
                    else target.成本
                end,
                updated_at = now()
            where target.id = target_id;

            delete from public.inventory_items
            where id = source_row.id;
        end if;
    end loop;
end;
$$;

update public.inventory_movements
set brand = 'SK', 品牌 = 'SK', material = '180g', 材质 = '180g'
where department = 'DTF'
  and coalesce(nullif(brand, ''), nullif(品牌, '')) = 'SK'
  and coalesce(nullif(material, ''), nullif(材质, '')) = '160g';

update public.inventory_sku_imports
set brand = 'SK', 品牌 = 'SK', material = '180g', 材质 = '180g'
where department = 'DTF'
  and coalesce(nullif(brand, ''), nullif(品牌, '')) = 'SK'
  and coalesce(nullif(material, ''), nullif(材质, '')) = '160g';

update public.inventory_snapshots
set brand = 'SK', material = '180g'
where department = 'DTF'
  and brand = 'SK'
  and material = '160g';

update public.inventory_container_imports
set brand = 'SK', 品牌 = 'SK', material = '180g', 材质 = '180g'
where department = 'DTF'
  and coalesce(nullif(brand, ''), nullif(品牌, '')) = 'SK'
  and coalesce(nullif(material, ''), nullif(材质, '')) = '160g';

commit;

select
    material,
    color,
    size,
    quantity
from public.inventory_items
where department = 'DTF'
  and brand = 'SK'
order by material, color, size;
