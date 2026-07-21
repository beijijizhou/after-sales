begin;

alter table public.inventory_items
alter column unit_cost type numeric(14, 4)
using round(unit_cost::numeric, 4);

alter table public.inventory_items
alter column 成本 type numeric(14, 4)
using round(成本::numeric, 4);

alter table public.inventory_movements
alter column unit_cost type numeric(14, 4)
using round(unit_cost::numeric, 4);

alter table public.inventory_movements
alter column 成本 type numeric(14, 4)
using round(成本::numeric, 4);

alter table public.inventory_sku_imports
alter column unit_cost type numeric(14, 4)
using round(unit_cost::numeric, 4);

alter table public.inventory_sku_imports
alter column 成本 type numeric(14, 4)
using round(成本::numeric, 4);

alter table public.inventory_container_imports
alter column unit_cost type numeric(14, 4)
using round(unit_cost::numeric, 4);

alter table public.inventory_container_imports
alter column 成本 type numeric(14, 4)
using round(成本::numeric, 4);

alter table public.inventory_snapshots
alter column unit_cost type numeric(14, 4)
using round(unit_cost::numeric, 4);

commit;
notify pgrst, 'reload schema';

select
    table_name,
    column_name,
    numeric_precision,
    numeric_scale
from information_schema.columns
where table_schema = 'public'
  and table_name in (
      'inventory_items', 'inventory_movements',
      'inventory_sku_imports', 'inventory_container_imports',
      'inventory_snapshots', 'inventory_cost_lots',
      'inventory_cost_allocations'
  )
  and column_name in ('unit_cost', '成本')
order by table_name, column_name;
