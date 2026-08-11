begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_stocktake_batches (
    batch_id uuid primary key,
    department text not null,
    category text,
    business_date date not null,
    item_count integer not null,
    total_before bigint not null,
    total_target bigint not null,
    total_difference bigint not null,
    created_by text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.inventory_stocktake_lines (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references public.inventory_stocktake_batches(batch_id),
    inventory_item_id uuid not null references public.inventory_items(id),
    brand text not null default '',
    material text not null,
    color text not null default '',
    size text not null default '',
    quantity_before integer not null,
    target_quantity integer not null check (target_quantity >= 0),
    quantity_difference integer not null,
    quantity_after integer not null,
    reason text,
    unique (batch_id, inventory_item_id)
);

create index if not exists inventory_stocktake_batches_date_idx
on public.inventory_stocktake_batches (business_date desc, created_at desc);

drop function if exists public.apply_inventory_stocktake_batch(
    text, text, jsonb, uuid, text
);

create or replace function public.apply_inventory_stocktake_batch(
    p_department text,
    p_category text,
    p_rows jsonb,
    p_batch_id uuid default gen_random_uuid(),
    p_created_by text default 'system'
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    stocktake_row jsonb;
    current_item public.inventory_items;
    effective_batch_id uuid := coalesce(p_batch_id, gen_random_uuid());
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
    normalized_department text := coalesce(nullif(trim(p_department), ''), 'DTF');
    normalized_category text := nullif(trim(coalesce(p_category, '')), '');
    normalized_brand text;
    normalized_material text;
    normalized_color text;
    normalized_size text;
    target_quantity integer;
    quantity_before integer;
    quantity_difference integer;
    business_date date;
    adjustment_rows jsonb := '[]'::jsonb;
    audit_rows jsonb := '[]'::jsonb;
begin
    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
        raise exception '库存设置批次不能为空';
    end if;

    business_date := coalesce(
        (p_rows->0->>'movement_date')::date,
        (now() at time zone 'America/New_York')::date
    );

    for stocktake_row in
        select value
        from jsonb_array_elements(p_rows)
        order by
            value->>'material', value->>'brand', value->>'color', value->>'size'
    loop
        if coalesce(
            (stocktake_row->>'movement_date')::date, business_date
        ) <> business_date then
            raise exception '同一库存设置批次只能使用一个业务日期';
        end if;
        normalized_brand := coalesce(trim(stocktake_row->>'brand'), '');
        normalized_material := coalesce(trim(stocktake_row->>'material'), '');
        normalized_color := coalesce(trim(stocktake_row->>'color'), '');
        normalized_size := upper(coalesce(trim(stocktake_row->>'size'), ''));
        target_quantity := (stocktake_row->>'target_quantity')::integer;
        if normalized_material = '' or target_quantity < 0 then
            raise exception '库存设置的材质不能为空，目标库存不能小于 0';
        end if;

        select * into current_item
        from public.inventory_items
        where department = normalized_department
          and coalesce(category, '') = coalesce(normalized_category, '')
          and brand = normalized_brand
          and material = normalized_material
          and coalesce(color, '') = normalized_color
          and coalesce(size, '') = normalized_size
        for update;

        if current_item.id is null and target_quantity = 0 then
            continue;
        end if;
        if current_item.id is null then
            raise exception '未找到需要设置的 SKU：% % % %',
                normalized_material, normalized_brand,
                normalized_color, normalized_size;
        end if;
        quantity_before := current_item.quantity;
        quantity_difference := target_quantity - quantity_before;

        audit_rows := audit_rows || jsonb_build_array(jsonb_build_object(
            'inventory_item_id', current_item.id,
            'brand', normalized_brand,
            'material', normalized_material,
            'color', normalized_color,
            'size', normalized_size,
            'quantity_before', quantity_before,
            'target_quantity', target_quantity,
            'quantity_difference', quantity_difference,
            'reason', coalesce(stocktake_row->>'reason', '库存盘点设置')
        ));
        if quantity_difference <> 0 then
            adjustment_rows := adjustment_rows || jsonb_build_array(
                jsonb_build_object(
                    'brand', normalized_brand,
                    'material', normalized_material,
                    'color', normalized_color,
                    'size', normalized_size,
                    'quantity_change', quantity_difference,
                    'movement_date', business_date,
                    'reason', coalesce(stocktake_row->>'reason', '库存盘点设置'),
                    'source_type', 'bulk'
                )
            );
        end if;
    end loop;

    if jsonb_array_length(adjustment_rows) > 0 then
        perform public.apply_inventory_adjustment_batch(
            normalized_department, normalized_category, adjustment_rows,
            effective_batch_id, effective_user, 'bulk'
        );
    end if;

    insert into public.inventory_stocktake_batches (
        batch_id, department, category, business_date, item_count,
        total_before, total_target, total_difference, created_by
    )
    select
        effective_batch_id, normalized_department, normalized_category,
        business_date, count(*)::integer,
        sum((value->>'quantity_before')::integer),
        sum((value->>'target_quantity')::integer),
        sum((value->>'quantity_difference')::integer), effective_user
    from jsonb_array_elements(audit_rows);

    insert into public.inventory_stocktake_lines (
        batch_id, inventory_item_id, brand, material, color, size,
        quantity_before, target_quantity, quantity_difference,
        quantity_after, reason
    )
    select
        effective_batch_id, (value->>'inventory_item_id')::uuid,
        value->>'brand', value->>'material', value->>'color', value->>'size',
        (value->>'quantity_before')::integer,
        (value->>'target_quantity')::integer,
        (value->>'quantity_difference')::integer,
        (value->>'target_quantity')::integer, value->>'reason'
    from jsonb_array_elements(audit_rows);

    return effective_batch_id;
end;
$$;

grant select on public.inventory_stocktake_batches,
    public.inventory_stocktake_lines to anon, authenticated, service_role;
grant execute on function public.apply_inventory_stocktake_batch(
    text, text, jsonb, uuid, text
) to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
