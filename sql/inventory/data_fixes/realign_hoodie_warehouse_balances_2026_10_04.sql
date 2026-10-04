-- Date: 2026-10-04
-- Scope: DTF / 卫衣 rows in inventory_warehouse_balances only.
-- Prerequisite: ../warehouses/06_warehouse_sync_style.sql is installed.
--
-- Before that fix, hoodie movements were synchronized to a sibling style's
-- warehouse balance. The warehouse-25 total still equals the hoodie total,
-- but individual SKU balances drifted. No hoodie stock has been transferred
-- to warehouse 60 or 70, so every hoodie SKU's warehouse-25 balance must
-- equal its company-wide quantity. inventory_items is not changed.
--
-- Precheck (expect: drift_rows > 0, non_25_quantity = 0):
--   select
--       count(*) filter (
--           where i.quantity <> coalesce(b25.quantity, 0)
--       ) as drift_rows,
--       coalesce(sum(other.quantity), 0) as non_25_quantity
--   from public.inventory_items i
--   left join public.inventory_warehouse_balances b25
--     on b25.inventory_item_id = i.id and b25.warehouse_code = '25'
--   left join public.inventory_warehouse_balances other
--     on other.inventory_item_id = i.id and other.warehouse_code <> '25'
--   where i.department = 'DTF' and i.category = '卫衣';
-- Verification: rerun the precheck after this script; drift_rows must be 0.
begin;

do $$
begin
    if exists (
        select 1
        from public.inventory_items i
        join public.inventory_warehouse_balances b
          on b.inventory_item_id = i.id
        where i.department = 'DTF' and i.category = '卫衣'
          and b.warehouse_code <> '25' and b.quantity <> 0
    ) then
        raise exception '卫衣在 25 仓以外已有库存，不能按整仓对齐';
    end if;
end;
$$;

insert into public.inventory_warehouse_balances (
    inventory_item_id, warehouse_code, quantity
)
select i.id, '25', i.quantity
from public.inventory_items i
where i.department = 'DTF' and i.category = '卫衣'
  and (
      i.quantity <> 0
      or exists (
          select 1 from public.inventory_warehouse_balances b
          where b.inventory_item_id = i.id and b.warehouse_code = '25'
      )
  )
on conflict (inventory_item_id, warehouse_code) do update
set quantity = excluded.quantity, updated_at = now()
where public.inventory_warehouse_balances.quantity <> excluded.quantity;

commit;
