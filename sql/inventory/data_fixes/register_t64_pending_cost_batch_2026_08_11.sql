-- T64 2026-08-11 到货成本批次登记。
-- 库存数量已经包含本批货物；此记录不修改 inventory_items 或流水。
-- 已确认为白色 3XL；单价先使用该 SKU 现有成本 $1.4500，待复核。

begin;

insert into public.inventory_pending_cost_batches (
    id, business_date, department, category, brand, material,
    color, size, quantity, unit_cost, source_type, inventory_effect,
    status, note, created_by
)
values (
    'f9d0a62a-e0cf-4b1e-b59b-7001c7b9a064',
    date '2026-08-11', 'DTF', '黑白短袖', 'T64', '160g',
    '白', '3XL', 10800, 1.4500, 'bulk', 'already_in_inventory',
    'ready_to_allocate',
    'T64 白色 3XL 到货 10,800 件；库存已包含，本批次仅补成本，不重复入库；单价 $1.4500 待复核',
    'Andy'
)
on conflict (id) do update set
    quantity = excluded.quantity,
    unit_cost = excluded.unit_cost,
    status = excluded.status,
    note = excluded.note,
    updated_at = now();

commit;

select
    business_date, department, category, brand, material,
    color, size, quantity, unit_cost, status, inventory_effect, note
from public.inventory_pending_cost_batches
where id = 'f9d0a62a-e0cf-4b1e-b59b-7001c7b9a064';
