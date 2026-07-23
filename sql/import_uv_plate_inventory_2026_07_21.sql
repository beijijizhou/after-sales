-- UV 牌类期初库存。型号沿用 inventory_items.size 字段。
-- 只导入尚不存在的 SKU；重复运行不会覆盖后续库存变化。

begin;

with desired(material, model, units_per_box, box_count, quantity) as (
    values
        ('铁牌', '2030', 100,   0,      0),
        ('铁牌', '1040', 100,  44,   4400),
        ('铁牌', '1530', 100, 148,  14800),
        ('铝牌', '2030', 200, 217,  43400),
        ('铝牌', 'YUAN', 300, 358, 107400),
        ('铁牌', '3040',  50, 727,  36350),
        ('铁牌', '盾牌',  60,  84,   5040),
        ('铝牌', '爱心', 300,   0,      0)
),
inserted as (
    insert into public.inventory_items (
        department, category, brand, material, color, size,
        unit_cost, quantity, 品牌, 材质, 成本
    )
    select
        'UV', '牌类', '', material, '白', model,
        0, quantity, '', material, 0
    from desired
    on conflict do nothing
    returning
        department, category, brand, material, color, size,
        unit_cost, quantity, 品牌, 材质, 成本
)
insert into public.inventory_sku_imports (
    department, category, brand, material, color, size,
    initial_quantity, unit_cost, import_date, 品牌, 材质, 成本
)
select
    department, category, brand, material, color, size,
    quantity, unit_cost,
    (now() at time zone 'America/New_York')::date,
    品牌, 材质, 成本
from inserted;

commit;

notify pgrst, 'reload schema';
