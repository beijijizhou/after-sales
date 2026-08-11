-- 08/10 库存设置曾被旧逻辑标记为正常入库，并继承 SKU 旧单价。
-- 此修复只取消自动继承的批次单价，不改库存数量和流水。

begin;

update public.inventory_cost_lots
set unit_cost = null
where batch_id = '4ca73b32-49de-431d-b8fe-7461504821c0'
  and reversed_at is null;

update public.inventory_cost_allocations allocation
set unit_cost = null
from public.inventory_cost_lots lot
where allocation.cost_lot_id = lot.id
  and lot.batch_id = '4ca73b32-49de-431d-b8fe-7461504821c0'
  and allocation.reversed_at is null;

update public.inventory_movements
set unit_cost = 0,
    "成本" = 0,
    source_type = 'stocktake'
where batch_id = '4ca73b32-49de-431d-b8fe-7461504821c0';

commit;

select
    count(*) as cost_lot_count,
    sum(received_quantity) as quantity,
    count(unit_cost) as priced_lot_count
from public.inventory_cost_lots
where batch_id = '4ca73b32-49de-431d-b8fe-7461504821c0'
  and reversed_at is null;
