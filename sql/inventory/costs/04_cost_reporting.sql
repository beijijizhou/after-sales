begin;

create or replace view public.inventory_cost_source_summary
with (security_invoker = true)
as
select
    item.id as inventory_item_id,
    item.department,
    item.category,
    item.brand,
    item.material,
    item.color,
    item.size,
    item.quantity as inventory_quantity,
    coalesce(sum(lot.remaining_quantity) filter (
        where lot.reversed_at is null
    ), 0)::integer as tracked_quantity,
    coalesce(sum(lot.remaining_quantity) filter (
        where lot.reversed_at is null
          and lot.source_type = 'transfer'
    ), 0)::integer as transfer_quantity,
    coalesce(sum(lot.remaining_quantity) filter (
        where lot.reversed_at is null
          and lot.source_type <> 'transfer'
    ), 0)::integer as regular_quantity,
    coalesce(sum(
        lot.remaining_quantity * lot.unit_cost
    ) filter (
        where lot.reversed_at is null
          and lot.source_type = 'transfer'
    ), 0)::numeric(16, 2) as transfer_inventory_value,
    coalesce(sum(
        lot.remaining_quantity * lot.unit_cost
    ) filter (
        where lot.reversed_at is null
          and lot.source_type <> 'transfer'
    ), 0)::numeric(16, 2) as regular_inventory_value,
    coalesce(sum(lot.remaining_quantity) filter (
        where lot.reversed_at is null
          and lot.unit_cost is null
    ), 0)::integer as missing_cost_quantity,
    (
        select bulk_lot.unit_cost
        from public.inventory_cost_lots bulk_lot
        where bulk_lot.inventory_item_id = item.id
          and bulk_lot.source_type in ('bulk', 'opening')
          and bulk_lot.reversed_at is null
          and bulk_lot.unit_cost is not null
        order by bulk_lot.movement_date desc, bulk_lot.created_at desc
        limit 1
    ) as latest_regular_unit_cost,
    (
        select transfer_lot.unit_cost
        from public.inventory_cost_lots transfer_lot
        where transfer_lot.inventory_item_id = item.id
          and transfer_lot.source_type = 'transfer'
          and transfer_lot.reversed_at is null
          and transfer_lot.unit_cost is not null
        order by transfer_lot.movement_date desc, transfer_lot.created_at desc
        limit 1
    ) as latest_transfer_unit_cost
from public.inventory_items item
left join public.inventory_cost_lots lot
    on lot.inventory_item_id = item.id
group by item.id;

grant select on public.inventory_cost_source_summary
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
