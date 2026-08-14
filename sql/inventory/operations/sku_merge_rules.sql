-- Prerequisite: inventory_reclassification_batches.sql.
-- Installs persistent, auditable SKU merge rules without rewriting history.

begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_sku_merge_rules (
    id uuid primary key default gen_random_uuid(),
    department text not null,
    category text not null,
    source_brand text not null,
    target_brand text not null,
    material text not null,
    color text not null,
    status text not null default 'active'
        check (status in ('active', 'inactive')),
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    deactivated_by text,
    deactivated_at timestamptz,
    check (trim(source_brand) <> trim(target_brand))
);

create unique index if not exists inventory_sku_merge_rules_active_source
on public.inventory_sku_merge_rules (
    department, category, source_brand, material, color
)
where status = 'active';

create index if not exists inventory_sku_merge_rules_target_idx
on public.inventory_sku_merge_rules (
    department, category, target_brand, material, color
);

create or replace function public.merge_inventory_sku_group(
    p_department text,
    p_category text,
    p_source_brand text,
    p_target_brand text,
    p_material text,
    p_color text,
    p_business_date date,
    p_operated_by text default 'system'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_batch_id uuid := gen_random_uuid();
    v_batch_key text := 'sku-merge-' || gen_random_uuid()::text;
    v_source public.inventory_items%rowtype;
    v_target public.inventory_items%rowtype;
    v_target_brand_id uuid;
    v_target_before integer;
    v_merged_cost numeric;
    v_total integer := 0;
    v_sku_count integer := 0;
begin
    if trim(coalesce(p_source_brand, '')) = ''
       or trim(coalesce(p_target_brand, '')) = ''
       or trim(p_source_brand) = trim(p_target_brand) then
        raise exception '来源品牌和目标品牌必须不同且不能为空';
    end if;

    perform 1 from public.inventory_items
    where department = p_department and category = p_category
      and brand = p_source_brand and material = p_material and color = p_color
    for update;
    if not found then
        raise exception '没有找到来源 SKU 组';
    end if;

    select id into v_target_brand_id
    from public.inventory_brands
    where trim(name) = trim(p_target_brand) and is_active = true
    order by created_at limit 1;
    if v_target_brand_id is null then
        raise exception '目标品牌不存在或未启用';
    end if;

    select coalesce(sum(quantity), 0)::integer, count(*)::integer
    into v_total, v_sku_count
    from public.inventory_items
    where department = p_department and category = p_category
      and brand = p_source_brand and material = p_material and color = p_color;

    insert into public.inventory_reclassification_batches (
        id, batch_key, business_date, department, category,
        source_scope, target_scope, reason, total_quantity, status, created_by
    ) values (
        v_batch_id, v_batch_key, p_business_date, p_department, p_category,
        concat_ws('｜', p_source_brand, p_material, p_color),
        concat_ws('｜', p_target_brand, p_material, p_color),
        'SKU 管理并入规则；当前库存转移，历史流水保留来源身份',
        v_total, 'completed', coalesce(nullif(p_operated_by, ''), 'system')
    );

    for v_source in
        select * from public.inventory_items
        where department = p_department and category = p_category
          and brand = p_source_brand and material = p_material and color = p_color
        order by size for update
    loop
        v_target := null;
        select * into v_target from public.inventory_items
        where department = p_department and category = p_category
          and brand = p_target_brand and material = p_material
          and color = p_color and size = v_source.size
        for update;

        if v_target.id is null then
            insert into public.inventory_items (
                category, 品牌, 材质, color, size, 成本, quantity,
                department, brand, material, unit_cost,
                department_id, category_id, brand_id, sku_code, sku_name,
                model, unit, is_active, created_by
            ) values (
                v_source.category, p_target_brand, v_source.material,
                v_source.color, v_source.size, 0, 0,
                v_source.department, p_target_brand, v_source.material, 0,
                v_source.department_id, v_source.category_id, v_target_brand_id,
                'SKU-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10)),
                concat_ws(' ', v_source.category, p_target_brand,
                    v_source.material, v_source.color, v_source.size),
                v_source.model, v_source.unit, true,
                coalesce(nullif(p_operated_by, ''), 'system')
            ) returning * into v_target;
        end if;

        v_target_before := v_target.quantity;
        v_merged_cost := case
            when v_target.quantity + v_source.quantity > 0 then round((
                coalesce(v_target.unit_cost, 0) * v_target.quantity
                + coalesce(v_source.unit_cost, 0) * v_source.quantity
            ) / (v_target.quantity + v_source.quantity), 4)
            else coalesce(v_target.unit_cost, v_source.unit_cost, 0)
        end;

        insert into public.inventory_warehouse_balances (
            inventory_item_id, warehouse_code, quantity, location_note
        )
        select v_target.id, warehouse_code, quantity,
            coalesce(location_note, 'SKU并入：' || p_source_brand || '→' || p_target_brand)
        from public.inventory_warehouse_balances
        where inventory_item_id = v_source.id and quantity > 0
        on conflict (inventory_item_id, warehouse_code) do update
        set quantity = public.inventory_warehouse_balances.quantity + excluded.quantity,
            updated_at = now();

        update public.inventory_warehouse_balances
        set quantity = 0, updated_at = now()
        where inventory_item_id = v_source.id;

        update public.inventory_cost_lots
        set inventory_item_id = v_target.id,
            note = concat_ws('｜', nullif(note, ''),
                'SKU并入：' || p_source_brand || '→' || p_target_brand)
        where inventory_item_id = v_source.id and reversed_at is null;

        update public.inventory_items
        set quantity = v_target_before + v_source.quantity,
            unit_cost = v_merged_cost, 成本 = v_merged_cost,
            is_active = true, updated_at = now()
        where id = v_target.id;

        update public.inventory_items
        set quantity = 0, is_active = false, updated_at = now()
        where id = v_source.id;

        if v_source.quantity > 0 then
            insert into public.inventory_reclassification_lines (
                batch_id, source_item_id, target_item_id, material, color, size,
                source_brand, target_brand, quantity,
                source_quantity_before, source_quantity_after,
                target_quantity_before, target_quantity_after
            ) values (
                v_batch_id, v_source.id, v_target.id, p_material, p_color,
                v_source.size, p_source_brand, p_target_brand, v_source.quantity,
                v_source.quantity, 0, v_target_before,
                v_target_before + v_source.quantity
            );
        end if;
    end loop;

    update public.inventory_sku_merge_rules
    set status = 'inactive', deactivated_by = p_operated_by,
        deactivated_at = now()
    where department = p_department and category = p_category
      and source_brand = p_source_brand and material = p_material
      and color = p_color and status = 'active';

    insert into public.inventory_sku_merge_rules (
        department, category, source_brand, target_brand, material, color,
        status, created_by
    ) values (
        p_department, p_category, p_source_brand, p_target_brand,
        p_material, p_color, 'active',
        coalesce(nullif(p_operated_by, ''), 'system')
    );

    update public.inventory_container_imports
    set brand = p_target_brand, 品牌 = p_target_brand,
        note = concat_ws('；', nullif(note, ''),
            'SKU并入：' || p_source_brand || '→' || p_target_brand)
    where department = p_department and category = p_category
      and brand = p_source_brand and material = p_material and color = p_color
      and status <> '已入库';

    perform public.create_inventory_snapshot(
        p_department, p_category, p_business_date
    );

    return jsonb_build_object(
        'batch_id', v_batch_id, 'moved_quantity', v_total,
        'affected_skus', v_sku_count, 'source_brand', p_source_brand,
        'target_brand', p_target_brand
    );
end;
$$;

create or replace function public.redirect_merged_container_sku()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    v_target_brand text;
begin
    select target_brand into v_target_brand
    from public.inventory_sku_merge_rules
    where department = new.department
      and category = coalesce(new.category, '')
      and source_brand = coalesce(new.brand, '')
      and material = coalesce(new.material, '')
      and color = coalesce(new.color, '')
      and status = 'active'
    order by created_at desc limit 1;
    if v_target_brand is not null then
        new.brand := v_target_brand;
        new.品牌 := v_target_brand;
        new.note := concat_ws('；', nullif(new.note, ''), 'SKU并入自动转入');
    end if;
    return new;
end;
$$;

drop trigger if exists inventory_container_merge_redirect
on public.inventory_container_imports;
create trigger inventory_container_merge_redirect
before insert or update of department, category, brand, material, color
on public.inventory_container_imports
for each row execute function public.redirect_merged_container_sku();

grant select on public.inventory_sku_merge_rules
to anon, authenticated, service_role;
grant execute on function public.merge_inventory_sku_group(
    text, text, text, text, text, text, date, text
) to authenticated, service_role;

commit;

notify pgrst, 'reload schema';
