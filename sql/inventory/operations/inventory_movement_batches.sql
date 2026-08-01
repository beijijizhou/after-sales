begin;

create extension if not exists pgcrypto;

alter table public.inventory_movements
add column if not exists batch_id uuid;

alter table public.inventory_movements
add column if not exists reversal_of_batch_id uuid;

alter table public.inventory_movements
add column if not exists created_by text;

update public.inventory_movements
set created_by = 'a'
where created_by is null
   or trim(created_by) = ''
   or created_by in ('历史记录', 'system');

update public.inventory_movements
set batch_id = md5(concat_ws(
    '|', date_trunc('minute', created_at)::text, movement_date::text,
    coalesce(department, ''), coalesce(category, ''), coalesce(reason, ''),
    case when quantity_change >= 0 then 'in' else 'out' end
))::uuid
where batch_id is null;

alter table public.inventory_movements alter column batch_id set default gen_random_uuid();
alter table public.inventory_movements alter column batch_id set not null;
alter table public.inventory_movements alter column created_by set default 'system';
alter table public.inventory_movements alter column created_by set not null;

create index if not exists inventory_movements_batch_id_idx
on public.inventory_movements (batch_id);

create index if not exists inventory_movements_reversal_of_batch_idx
on public.inventory_movements (reversal_of_batch_id)
where reversal_of_batch_id is not null;

create table if not exists public.inventory_movement_reversals (
    original_batch_id uuid primary key,
    reversal_batch_id uuid not null unique,
    reversed_by text not null default 'system',
    created_at timestamptz not null default now()
);

alter table public.inventory_movement_reversals
add column if not exists reversed_by text not null default 'system';

update public.inventory_movement_reversals
set reversed_by = 'a'
where reversed_by is null
   or trim(reversed_by) = ''
   or reversed_by in ('历史记录', 'system');

drop function if exists public.apply_inventory_adjustment_batch(text, text, jsonb, uuid);
drop function if exists public.apply_inventory_adjustment_batch(text, text, jsonb, uuid, text);

create or replace function public.apply_inventory_adjustment_batch(
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
    adjustment_row jsonb;
    current_item public.inventory_items;
    effective_batch_id uuid := coalesce(p_batch_id, gen_random_uuid());
    normalized_department text := coalesce(nullif(trim(p_department), ''), 'DTF');
    normalized_category text := nullif(trim(coalesce(p_category, '')), '');
    normalized_brand text;
    normalized_material text;
    normalized_color text;
    normalized_size text;
    quantity_change integer;
    movement_date date;
    has_unit_cost boolean;
    supplied_unit_cost numeric;
begin
    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
        raise exception '库存调整批次不能为空';
    end if;

    for adjustment_row in select * from jsonb_array_elements(p_rows)
    loop
        normalized_brand := coalesce(trim(adjustment_row->>'brand'), '');
        normalized_material := coalesce(trim(adjustment_row->>'material'), '');
        normalized_color := coalesce(trim(adjustment_row->>'color'), '');
        normalized_size := upper(coalesce(trim(adjustment_row->>'size'), ''));
        quantity_change := (adjustment_row->>'quantity_change')::integer;
        movement_date := coalesce(
            (adjustment_row->>'movement_date')::date,
            (now() at time zone 'America/New_York')::date
        );
        has_unit_cost := adjustment_row ? 'unit_cost'
            and nullif(adjustment_row->>'unit_cost', '') is not null;
        supplied_unit_cost := case
            when has_unit_cost then (adjustment_row->>'unit_cost')::numeric
            else 0
        end;

        select * into current_item
        from public.inventory_items
        where department = normalized_department
          and coalesce(category, '') = coalesce(normalized_category, '')
          and brand = normalized_brand
          and material = normalized_material
          and coalesce(color, '') = normalized_color
          and coalesce(size, '') = normalized_size
        for update;

        if current_item.id is null then
            insert into public.inventory_items (
                department, category, brand, material, color, size,
                unit_cost, quantity, 品牌, 材质, 成本
            ) values (
                normalized_department, normalized_category, normalized_brand,
                normalized_material, normalized_color, normalized_size,
                supplied_unit_cost, 0, normalized_brand, normalized_material,
                supplied_unit_cost
            ) returning * into current_item;
        end if;

        if current_item.quantity + quantity_change < 0 then
            raise exception '库存不足：% % % %，当前库存 %，调整 %',
                normalized_brand, normalized_material, normalized_color,
                normalized_size, current_item.quantity, quantity_change;
        end if;

        update public.inventory_items
        set quantity = quantity + quantity_change,
            unit_cost = case when has_unit_cost then supplied_unit_cost else unit_cost end,
            成本 = case when has_unit_cost then supplied_unit_cost else 成本 end,
            updated_at = now()
        where id = current_item.id
        returning * into current_item;

        insert into public.inventory_movements (
            department, category, brand, material, color, size,
            quantity_change, quantity_after, movement_date, reason,
            batch_id, created_by, unit_cost, 品牌, 材质, 成本
        ) values (
            normalized_department, normalized_category, normalized_brand,
            normalized_material, normalized_color, normalized_size,
            quantity_change, current_item.quantity, movement_date,
            adjustment_row->>'reason', effective_batch_id,
            coalesce(nullif(trim(p_created_by), ''), 'system'),
            current_item.unit_cost, normalized_brand, normalized_material,
            current_item.unit_cost
        );
    end loop;

    return effective_batch_id;
end;
$$;

grant execute on function public.apply_inventory_adjustment_batch(text, text, jsonb, uuid, text)
to anon, authenticated, service_role;
grant select, insert on public.inventory_movement_reversals
to anon, authenticated, service_role;

commit;
notify pgrst, 'reload schema';
