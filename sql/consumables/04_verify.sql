select
    table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
      'consumable_items',
      'consumable_movement_batches',
      'consumable_movements'
  )
order by table_name;

select
    routine_name
from information_schema.routines
where routine_schema = 'public'
  and routine_name in (
      'apply_consumable_movement_batch',
      'reverse_consumable_movement_batch'
  )
order by routine_name;
