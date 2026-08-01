-- This query should return no rows. Any result means the SKU quantity and
-- active cost-lot quantity are inconsistent.
select
    inventory_item_id,
    department,
    category,
    brand,
    material,
    color,
    size,
    inventory_quantity,
    tracked_quantity,
    inventory_quantity - tracked_quantity as quantity_difference
from public.inventory_cost_source_summary
where inventory_quantity <> tracked_quantity
order by abs(inventory_quantity - tracked_quantity) desc;

-- Current inventory split by source.
select
    department,
    category,
    sum(regular_quantity) as regular_quantity,
    sum(transfer_quantity) as transfer_quantity,
    sum(missing_cost_quantity) as missing_cost_quantity
from public.inventory_cost_source_summary
group by department, category
order by department, category;

-- Confirm the latest function signatures exposed to PostgREST.
select
    proname,
    pg_get_function_identity_arguments(oid) as arguments
from pg_proc
where pronamespace = 'public'::regnamespace
  and proname in (
      'apply_inventory_adjustment_batch',
      'reverse_inventory_movement_batch'
  )
order by proname;
