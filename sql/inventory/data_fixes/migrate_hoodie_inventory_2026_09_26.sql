-- One-time, audited migration of the supplied hoodie workbook.
-- Run inventory_hoodie_style.sql first, then call:
--   select public.migrate_hoodie_inventory_2026_09_26('<human operator>');
begin;

create table if not exists public.inventory_hoodie_migration_runs (
    source_key text primary key,
    batch_id uuid not null unique,
    source_total integer not null,
    previous_total integer not null,
    difference integer not null,
    created_by text not null,
    created_at timestamptz not null default now()
);

create or replace function public.migrate_hoodie_inventory_2026_09_26(
    p_operator text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_source_key constant text := '衣服尺码数量_可编辑(1).xlsx|48705|2026-09-26';
    effective_user text := nullif(trim(p_operator), '');
    effective_batch_id uuid := gen_random_uuid();
    category_row public.inventory_categories%rowtype;
    brand_row public.inventory_brands%rowtype;
    old_item public.inventory_items%rowtype;
    target_item public.inventory_items%rowtype;
    seed_row record;
    movement_id uuid;
    previous_total integer;
    source_total integer;
begin
    if effective_user is null or lower(effective_user) = 'system' then
        raise exception '必须记录真实操作人';
    end if;
    if exists (
        select 1 from public.inventory_hoodie_migration_runs r
        where r.source_key = v_source_key
    ) then
        select batch_id into effective_batch_id
        from public.inventory_hoodie_migration_runs r
        where r.source_key = v_source_key;
        return effective_batch_id;
    end if;

    select c.* into category_row
    from public.inventory_categories c
    join public.inventory_departments d on d.id = c.department_id
    where d.code = 'DTF' and c.name = '卫衣';
    select * into brand_row from public.inventory_brands
    where lower(trim(name)) = lower('Haloo') limit 1;
    if category_row.id is null or brand_row.id is null then
        raise exception '缺少 DTF / 卫衣 / Haloo 主数据';
    end if;

    create temporary table hoodie_seed (
        material text not null,
        style text not null,
        color text not null,
        quantities integer[] not null
    ) on commit drop;
    insert into hoodie_seed values
        ('连帽','常规','黑',array[0,200,0,0,0,0,1900,2000]),
        ('连帽','常规','白',array[0,0,0,0,0,0,40,0]),
        ('连帽','常规','红',array[0,0,0,0,0,0,0,0]),
        ('连帽','常规','灰',array[0,360,360,200,300,0,780,100]),
        ('连帽','女款','黑',array[180,140,10,0,20,0,0,0]),
        ('连帽','女款-厚','黑',array[1470,3720,4670,1920,500,300,0,0]),
        ('连帽','女款-厚-彩','灰',array[374,300,300,360,480,420,0,0]),
        ('连帽','女款-厚-彩','藏青',array[15,0,700,0,0,0,0,0]),
        ('连帽','女款-彩','灰',array[0,0,0,580,0,0,0,0]),
        ('连帽','旧款-厚','黑',array[0,0,0,0,0,0,0,350]),
        ('连帽','旧款-厚-彩','粉色',array[45,183,319,133,220,210,70,70]),
        ('连帽','旧款-厚-彩','藏青',array[0,0,300,0,0,0,30,50]),
        ('连帽','旧款-厚-彩','红',array[0,0,15,0,0,60,100,130]),
        ('连帽','旧款-厚-彩','灰',array[60,15,40,25,0,0,0,0]),
        ('连帽','旧款-厚-彩','杏色',array[0,0,0,0,0,0,20,0]),
        ('连帽','旧款-彩','粉色',array[65,294,225,190,75,70,100,60]),
        ('圆领','常规','黑',array[0,1040,1000,2270,795,0,1190,1500]),
        ('圆领','常规','白',array[600,0,200,950,0,1250,0,350]),
        ('圆领','常规','红',array[0,0,0,0,0,0,0,0]),
        ('圆领','常规','灰',array[0,0,0,0,0,0,0,0]),
        ('圆领','旧款-厚','黑',array[300,1120,1920,2260,520,300,660,760]),
        ('圆领','旧款-厚-彩','粉色',array[2520,140,80,40,20,0,0,0]),
        ('圆领','旧款-彩','粉色',array[100,75,180,40,0,20,70,75]),
        ('圆领','旧款-彩','藏青',array[0,0,0,75,0,62,0,0]);

    select coalesce(sum(quantity), 0)::integer into previous_total
    from public.inventory_items
    where department = 'DTF' and category = '卫衣';
    select sum(quantity)::integer into source_total
    from hoodie_seed cross join lateral unnest(quantities) quantity;
    if source_total <> 48705 then
        raise exception '卫衣来源合计异常：%', source_total;
    end if;

    insert into public.inventory_materials (name, created_by)
    values ('连帽', effective_user), ('圆领', effective_user)
    on conflict do nothing;
    insert into public.inventory_category_materials (
        category_id, material_id, created_by
    )
    select category_row.id, m.id, effective_user
    from public.inventory_materials m
    where m.name in ('连帽', '圆领')
    on conflict do nothing;

    -- Close every old compressed SKU with an auditable outbound movement.
    for old_item in
        select * from public.inventory_items
        where department = 'DTF' and category = '卫衣' and style = ''
        for update
    loop
        if old_item.quantity <> 0 then
            insert into public.inventory_movements (
                department, category, brand, material, style, color, size,
                quantity_change, quantity_after, movement_date, reason,
                batch_id, created_by, source_type, unit_cost, 品牌, 材质, 成本
            ) values (
                'DTF','卫衣',old_item.brand,old_item.material,'',
                old_item.color,old_item.size,-old_item.quantity,0,'2026-09-26',
                '卫衣 SKU 重分类｜来源：衣服尺码数量_可编辑(1).xlsx',
                effective_batch_id,effective_user,null,old_item.unit_cost,
                old_item.brand,old_item.material,old_item.unit_cost
            ) returning id into movement_id;
            insert into public.inventory_cost_allocations (
                outbound_movement_id, cost_lot_id, quantity,
                unit_cost, source_type
            )
            select movement_id, id, remaining_quantity, unit_cost, source_type
            from public.inventory_cost_lots
            where inventory_item_id = old_item.id
              and reversed_at is null and remaining_quantity > 0;
            update public.inventory_cost_lots set remaining_quantity = 0
            where inventory_item_id = old_item.id
              and reversed_at is null and remaining_quantity > 0;
        end if;
        update public.inventory_items set
            quantity = 0, is_active = false, updated_at = now()
        where id = old_item.id;
    end loop;

    -- Recreate the exact 192 formal SKU rows (24 combinations × 8 sizes).
    for seed_row in
        select h.material, h.style, h.color, s.size, s.quantity
        from hoodie_seed h
        cross join lateral unnest(
            array['S','M','L','XL','2XL','3XL','4XL','5XL'], h.quantities
        ) as s(size, quantity)
    loop
        insert into public.inventory_items (
            department, category, brand, material, style, color, size,
            quantity, unit_cost, unit, is_active, created_by,
            department_id, category_id, brand_id, sku_code, sku_name,
            品牌, 材质, 成本
        ) values (
            'DTF','卫衣','Haloo',seed_row.material,seed_row.style,
            seed_row.color,seed_row.size,0,0,'件',true,effective_user,
            category_row.department_id,category_row.id,brand_row.id,
            'SKU-' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,10)),
            concat_ws(' ','卫衣','Haloo',seed_row.material,seed_row.style,
                seed_row.color,seed_row.size),
            'Haloo',seed_row.material,0
        ) on conflict (
            department, (coalesce(category, '')), brand, material, style,
            color, size
        ) do update set is_active = true, updated_at = now()
        returning * into target_item;
        if seed_row.quantity > 0 then
            update public.inventory_items set
                quantity = seed_row.quantity, updated_at = now()
            where id = target_item.id returning * into target_item;
            insert into public.inventory_movements (
                department, category, brand, material, style, color, size,
                quantity_change, quantity_after, movement_date, reason,
                batch_id, created_by, source_type, unit_cost, 品牌, 材质, 成本
            ) values (
                'DTF','卫衣','Haloo',seed_row.material,seed_row.style,
                seed_row.color,seed_row.size,seed_row.quantity,
                seed_row.quantity,'2026-09-26',
                '卫衣 SKU 重分类｜来源：衣服尺码数量_可编辑(1).xlsx',
                effective_batch_id,effective_user,'transfer',0,
                'Haloo',seed_row.material,0
            ) returning id into movement_id;
            insert into public.inventory_cost_lots (
                inventory_item_id,inbound_movement_id,batch_id,source_type,
                received_quantity,remaining_quantity,unit_cost,movement_date,
                note,created_by
            ) values (
                target_item.id,movement_id,effective_batch_id,'transfer',
                seed_row.quantity,seed_row.quantity,null,'2026-09-26',
                '卫衣 SKU 重分类｜来源：衣服尺码数量_可编辑(1).xlsx',
                effective_user
            );
        end if;
    end loop;

    insert into public.inventory_sku_change_log (
        department, old_identity, new_identity, affected_items,
        affected_quantity, changed_by
    ) values (
        'DTF',
        jsonb_build_object(
            'category','卫衣','structure','旧材质压缩结构',
            'quantity',previous_total
        ),
        jsonb_build_object(
            'category','卫衣',
            'hierarchy','材质 → 品牌 → 款式 → 颜色 → 尺码',
            'materials',jsonb_build_array('连帽','圆领'),
            'quantity',source_total,
            'source','衣服尺码数量_可编辑(1).xlsx'
        ),
        192, source_total, effective_user
    );
    insert into public.inventory_hoodie_migration_runs (
        source_key,batch_id,source_total,previous_total,difference,created_by
    ) values (
        v_source_key,effective_batch_id,source_total,previous_total,
        source_total - previous_total,effective_user
    );
    return effective_batch_id;
end;
$$;

revoke all on function public.migrate_hoodie_inventory_2026_09_26(text)
from public, anon, authenticated;
grant execute on function public.migrate_hoodie_inventory_2026_09_26(text)
to service_role;
grant select on public.inventory_hoodie_migration_runs to service_role;

commit;
notify pgrst, 'reload schema';
