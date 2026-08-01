begin;

-- Fix accidental blank brand for DTF / 黑白短袖 / CVC / 黑.
-- If Haloo rows already exist, merge blank-brand quantities into Haloo first.
with blank_brand_items as (
    select *
    from public.inventory_items
    where department = 'DTF'
      and category = '黑白短袖'
      and coalesce(brand, '') = ''
      and material = 'CVC'
      and color = '黑'
),
merged_items as (
    update public.inventory_items target
    set
        quantity = target.quantity + source.quantity,
        updated_at = now()
    from blank_brand_items source
    where target.department = source.department
      and coalesce(target.category, '') = coalesce(source.category, '')
      and target.brand = 'Haloo'
      and target.material = source.material
      and target.color = source.color
      and target.size = source.size
    returning source.id
)
delete from public.inventory_items
where id in (select id from merged_items);

update public.inventory_items
set
    brand = 'Haloo',
    品牌 = 'Haloo',
    updated_at = now()
where department = 'DTF'
  and category = '黑白短袖'
  and coalesce(brand, '') = ''
  and material = 'CVC'
  and color = '黑';

update public.inventory_movements
set
    brand = 'Haloo',
    品牌 = 'Haloo'
where department = 'DTF'
  and category = '黑白短袖'
  and coalesce(brand, '') = ''
  and material = 'CVC'
  and color = '黑';

update public.inventory_sku_imports
set
    brand = 'Haloo',
    品牌 = 'Haloo'
where department = 'DTF'
  and category = '黑白短袖'
  and coalesce(brand, '') = ''
  and material = 'CVC'
  and color = '黑';

commit;
