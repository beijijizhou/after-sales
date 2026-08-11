-- One-time current-inventory reclassification for the 2026-08-10 stocktake.
-- This is not a SKU master-data merge: source SKUs remain active and all
-- historical movements retain their original brands.

begin;

do $$
declare
    v_batch_id uuid := gen_random_uuid();
    v_misc_brand_id uuid;
    v_source record;
    v_target public.inventory_items%rowtype;
    v_source_total integer;
    v_target_before integer;
    v_total_before integer;
    v_total_after integer;
begin
    if exists (
        select 1
        from public.inventory_reclassification_batches
        where batch_key = 'stocktake-2026-08-10-160g-white-to-misc'
    ) then
        raise exception '该库存归类批次已经执行，不能重复执行';
    end if;

    select coalesce(sum(quantity), 0)::integer
    into v_source_total
    from public.inventory_items
    where department = 'DTF'
      and category = '黑白短袖'
      and material = '160g'
      and color = '白'
      and brand in ('Caribbean', 'Men''s');

    if v_source_total <> 49940 then
        raise exception '来源库存已变化：预期 49940，当前 %', v_source_total;
    end if;

    if exists (
        select 1
        from (
            values
                ('S', 4320), ('M', 0), ('L', 20360), ('XL', 4000),
                ('2XL', 1500), ('3XL', 7740), ('4XL', 4380),
                ('5XL', 7640)
        ) expected(size, quantity)
        left join lateral (
            select coalesce(sum(item.quantity), 0)::integer as quantity
            from public.inventory_items item
            where item.department = 'DTF'
              and item.category = '黑白短袖'
              and item.material = '160g'
              and item.color = '白'
              and item.brand in ('Caribbean', 'Men''s')
              and item.size = expected.size
        ) actual on true
        where actual.quantity <> expected.quantity
    ) then
        raise exception '来源尺码数量与 08/10 盘点单不一致，已停止归类';
    end if;

    if exists (
        select 1
        from public.inventory_items item
        where item.department = 'DTF'
          and item.category = '黑白短袖'
          and item.material = '160g'
          and item.color = '白'
          and item.brand in ('Caribbean', 'Men''s')
          and item.quantity <> coalesce((
              select sum(balance.quantity)::integer
              from public.inventory_warehouse_balances balance
              where balance.inventory_item_id = item.id
          ), 0)
    ) then
        raise exception '来源 SKU 的仓库分布与当前库存不一致，已停止归类';
    end if;

    if exists (
        select 1
        from public.inventory_items item
        where item.department = 'DTF'
          and item.category = '黑白短袖'
          and item.material = '160g'
          and item.color = '白'
          and item.brand in ('Caribbean', 'Men''s')
          and item.quantity <> coalesce((
              select sum(lot.remaining_quantity)::integer
              from public.inventory_cost_lots lot
              where lot.inventory_item_id = item.id
                and lot.reversed_at is null
          ), 0)
    ) then
        raise exception '来源 SKU 的成本批次数量与当前库存不一致，已停止归类';
    end if;

    select coalesce(sum(quantity), 0)::integer
    into v_total_before
    from public.inventory_items
    where department = 'DTF'
      and category = '黑白短袖'
      and material = '160g'
      and color = '白';

    select id into v_misc_brand_id
    from public.inventory_brands
    where lower(trim(name)) = lower('杂牌')
    order by created_at
    limit 1;

    if v_misc_brand_id is null then
        insert into public.inventory_brands (name, is_active, created_by)
        values ('杂牌', true, 'Andy')
        returning id into v_misc_brand_id;
    else
        update public.inventory_brands
        set is_active = true,
            updated_at = now()
        where id = v_misc_brand_id;
    end if;

    insert into public.inventory_reclassification_batches (
        id, batch_key, business_date, department, category,
        source_scope, target_scope, reason, total_quantity,
        status, created_by
    ) values (
        v_batch_id,
        'stocktake-2026-08-10-160g-white-to-misc',
        date '2026-08-10',
        'DTF',
        '黑白短袖',
        'Caribbean + Men''s｜160g｜白',
        '杂牌｜160g｜白',
        '08/10 品牌调动后的当前库存归类；不改变历史品牌',
        v_source_total,
        'completed',
        'Andy'
    );

    for v_source in
        select item.*
        from public.inventory_items item
        where item.department = 'DTF'
          and item.category = '黑白短袖'
          and item.material = '160g'
          and item.color = '白'
          and item.brand in ('Caribbean', 'Men''s')
          and item.quantity > 0
        order by
            case item.size
                when 'S' then 1 when 'M' then 2 when 'L' then 3
                when 'XL' then 4 when '2XL' then 5 when '3XL' then 6
                when '4XL' then 7 when '5XL' then 8 else 99
            end,
            item.brand
        for update
    loop
        v_target := null;

        select item.* into v_target
        from public.inventory_items item
        where item.department = v_source.department
          and item.category = v_source.category
          and item.brand = '杂牌'
          and item.material = v_source.material
          and item.color = v_source.color
          and item.size = v_source.size
        for update;

        if v_target.id is null then
            insert into public.inventory_items (
                category, 品牌, 材质, color, size, 成本, quantity,
                department, brand, material, unit_cost,
                department_id, category_id, brand_id,
                sku_code, sku_name, model, unit, is_active, created_by
            ) values (
                v_source.category, '杂牌', v_source.material,
                v_source.color, v_source.size, 0, 0,
                v_source.department, '杂牌', v_source.material, 0,
                v_source.department_id, v_source.category_id, v_misc_brand_id,
                'SKU-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10)),
                concat_ws(' ', v_source.category, '杂牌', v_source.material,
                    v_source.color, v_source.size),
                v_source.model, v_source.unit, true, 'Andy'
            )
            returning * into v_target;
        end if;

        v_target_before := v_target.quantity;

        insert into public.inventory_warehouse_balances (
            inventory_item_id, warehouse_code, quantity, location_note
        )
        select
            v_target.id,
            balance.warehouse_code,
            balance.quantity,
            coalesce(balance.location_note, '08/10 当前库存品牌归类')
        from public.inventory_warehouse_balances balance
        where balance.inventory_item_id = v_source.id
          and balance.quantity > 0
        on conflict (inventory_item_id, warehouse_code) do update
        set quantity = public.inventory_warehouse_balances.quantity
                + excluded.quantity,
            updated_at = now();

        update public.inventory_warehouse_balances
        set quantity = 0,
            updated_at = now()
        where inventory_item_id = v_source.id;

        update public.inventory_cost_lots
        set inventory_item_id = v_target.id,
            note = concat_ws('｜', nullif(note, ''),
                '08/10 当前库存品牌归类：' || v_source.brand || '→杂牌')
        where inventory_item_id = v_source.id
          and reversed_at is null
          and remaining_quantity > 0;

        update public.inventory_items
        set quantity = 0,
            updated_at = now()
        where id = v_source.id;

        update public.inventory_items
        set quantity = v_target_before + v_source.quantity,
            updated_at = now()
        where id = v_target.id;

        insert into public.inventory_reclassification_lines (
            batch_id, source_item_id, target_item_id,
            material, color, size, source_brand, target_brand, quantity,
            source_quantity_before, source_quantity_after,
            target_quantity_before, target_quantity_after
        ) values (
            v_batch_id, v_source.id, v_target.id,
            v_source.material, v_source.color, v_source.size,
            v_source.brand, '杂牌', v_source.quantity,
            v_source.quantity, 0,
            v_target_before, v_target_before + v_source.quantity
        );
    end loop;

    update public.inventory_items target
    set unit_cost = case
            when exists (
                select 1
                from public.inventory_cost_lots lot
                where lot.inventory_item_id = target.id
                  and lot.reversed_at is null
                  and lot.remaining_quantity > 0
                  and lot.unit_cost is null
            ) then 0
            else coalesce((
                select round(
                    sum(lot.remaining_quantity * lot.unit_cost)
                    / nullif(sum(lot.remaining_quantity), 0),
                    4
                )
                from public.inventory_cost_lots lot
                where lot.inventory_item_id = target.id
                  and lot.reversed_at is null
                  and lot.remaining_quantity > 0
            ), 0)
        end,
        成本 = case
            when exists (
                select 1
                from public.inventory_cost_lots lot
                where lot.inventory_item_id = target.id
                  and lot.reversed_at is null
                  and lot.remaining_quantity > 0
                  and lot.unit_cost is null
            ) then 0
            else coalesce((
                select round(
                    sum(lot.remaining_quantity * lot.unit_cost)
                    / nullif(sum(lot.remaining_quantity), 0),
                    4
                )
                from public.inventory_cost_lots lot
                where lot.inventory_item_id = target.id
                  and lot.reversed_at is null
                  and lot.remaining_quantity > 0
            ), 0)
        end,
        updated_at = now()
    where target.department = 'DTF'
      and target.category = '黑白短袖'
      and target.brand = '杂牌'
      and target.material = '160g'
      and target.color = '白';

    select coalesce(sum(quantity), 0)::integer
    into v_total_after
    from public.inventory_items
    where department = 'DTF'
      and category = '黑白短袖'
      and material = '160g'
      and color = '白';

    if v_total_after <> v_total_before then
        raise exception '归类前后总库存不一致：归类前 %，归类后 %',
            v_total_before, v_total_after;
    end if;

    if (
        select coalesce(sum(quantity), 0)
        from public.inventory_items
        where department = 'DTF'
          and category = '黑白短袖'
          and brand = '杂牌'
          and material = '160g'
          and color = '白'
    ) <> 49940 then
        raise exception '杂牌目标库存不是 49940，事务已回滚';
    end if;

    if exists (
        select 1
        from public.inventory_items
        where department = 'DTF'
          and category = '黑白短袖'
          and brand in ('Caribbean', 'Men''s')
          and material = '160g'
          and color = '白'
          and quantity <> 0
    ) then
        raise exception '来源品牌仍有未归类数量，事务已回滚';
    end if;
end;
$$;

commit;

select
    brand as 品牌,
    material as 材质,
    color as 颜色,
    sum(quantity) filter (where size = 'S') as "S",
    sum(quantity) filter (where size = 'M') as "M",
    sum(quantity) filter (where size = 'L') as "L",
    sum(quantity) filter (where size = 'XL') as "XL",
    sum(quantity) filter (where size = '2XL') as "2XL",
    sum(quantity) filter (where size = '3XL') as "3XL",
    sum(quantity) filter (where size = '4XL') as "4XL",
    sum(quantity) filter (where size = '5XL') as "5XL",
    sum(quantity) as 合计
from public.inventory_items
where department = 'DTF'
  and category = '黑白短袖'
  and brand = '杂牌'
  and material = '160g'
  and color = '白'
group by brand, material, color;
