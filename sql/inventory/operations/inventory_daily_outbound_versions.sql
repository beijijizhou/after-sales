begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_daily_outbound_batches (
    id uuid primary key default gen_random_uuid(),
    department text not null,
    category text not null,
    movement_date date not null,
    current_revision integer not null default 0,
    status text not null default 'active'
        check (status in ('active', 'voided')),
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text not null,
    updated_at timestamptz not null default now(),
    unique (department, category, movement_date)
);

create table if not exists public.inventory_daily_outbound_revisions (
    id uuid primary key default gen_random_uuid(),
    daily_outbound_batch_id uuid not null
        references public.inventory_daily_outbound_batches(id),
    revision_number integer not null,
    action text not null check (action in ('create', 'edit', 'void')),
    inventory_batch_id uuid,
    reversal_inventory_batch_id uuid,
    requested_total integer not null default 0,
    applied_total integer not null default 0,
    shortage_total integer not null default 0,
    note text,
    created_by text not null,
    created_at timestamptz not null default now(),
    unique (daily_outbound_batch_id, revision_number)
);

create table if not exists public.inventory_daily_outbound_lines (
    id uuid primary key default gen_random_uuid(),
    revision_id uuid not null
        references public.inventory_daily_outbound_revisions(id),
    brand text not null default '',
    material text not null,
    color text not null,
    size text not null,
    requested_quantity integer not null check (requested_quantity > 0),
    applied_quantity integer not null check (applied_quantity >= 0),
    shortage_quantity integer not null check (shortage_quantity >= 0),
    constraint inventory_daily_outbound_line_math_check
        check (requested_quantity = applied_quantity + shortage_quantity),
    unique (revision_id, brand, material, color, size)
);

create index if not exists idx_daily_outbound_revision_batch
on public.inventory_daily_outbound_revisions (
    daily_outbound_batch_id, revision_number desc
);

create index if not exists idx_daily_outbound_lines_revision
on public.inventory_daily_outbound_lines (revision_id);

create or replace function public.save_inventory_daily_outbound_revision(
    p_department text,
    p_category text,
    p_movement_date date,
    p_rows jsonb,
    p_created_by text,
    p_daily_outbound_batch_id uuid default null,
    p_note text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    logical_batch public.inventory_daily_outbound_batches%rowtype;
    previous_revision public.inventory_daily_outbound_revisions%rowtype;
    source_row jsonb;
    current_item public.inventory_items%rowtype;
    new_revision_id uuid;
    inventory_batch_id uuid;
    reversal_batch_id uuid;
    next_revision integer;
    requested integer;
    applied integer;
    shortage integer;
    requested_total integer := 0;
    applied_total integer := 0;
    shortage_total integer := 0;
    applied_rows jsonb := '[]'::jsonb;
    result_lines jsonb := '[]'::jsonb;
    effective_user text := coalesce(nullif(trim(p_created_by), ''), 'system');
begin
    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
        raise exception '每日出库不能为空';
    end if;

    if p_daily_outbound_batch_id is null then
        insert into public.inventory_daily_outbound_batches (
            department, category, movement_date, created_by, updated_by
        ) values (
            p_department, p_category, p_movement_date,
            effective_user, effective_user
        )
        on conflict (department, category, movement_date) do update
        set updated_by = excluded.updated_by,
            updated_at = now()
        returning * into logical_batch;
    else
        select * into logical_batch
        from public.inventory_daily_outbound_batches
        where id = p_daily_outbound_batch_id
        for update;
        if logical_batch.id is null then
            raise exception '没有找到每日出库业务批次';
        end if;
    end if;

    select * into previous_revision
    from public.inventory_daily_outbound_revisions
    where daily_outbound_batch_id = logical_batch.id
      and revision_number = logical_batch.current_revision;

    if previous_revision.inventory_batch_id is not null then
        reversal_batch_id := public.reverse_inventory_movement_batch(
            previous_revision.inventory_batch_id, effective_user
        );
    end if;

    next_revision := logical_batch.current_revision + 1;

    for source_row in select * from jsonb_array_elements(p_rows)
    loop
        requested := greatest((source_row->>'requested_quantity')::integer, 0);
        if requested = 0 then
            continue;
        end if;

        select * into current_item
        from public.inventory_items
        where department = p_department
          and category = p_category
          and brand = coalesce(trim(source_row->>'brand'), '')
          and material = coalesce(trim(source_row->>'material'), '')
          and color = coalesce(trim(source_row->>'color'), '')
          and size = upper(coalesce(trim(source_row->>'size'), ''))
        for update;

        applied := least(requested, coalesce(current_item.quantity, 0));
        shortage := requested - applied;
        requested_total := requested_total + requested;
        applied_total := applied_total + applied;
        shortage_total := shortage_total + shortage;

        result_lines := result_lines || jsonb_build_array(jsonb_build_object(
            'brand', coalesce(trim(source_row->>'brand'), ''),
            'material', coalesce(trim(source_row->>'material'), ''),
            'color', coalesce(trim(source_row->>'color'), ''),
            'size', upper(coalesce(trim(source_row->>'size'), '')),
            'requested_quantity', requested,
            'applied_quantity', applied,
            'shortage_quantity', shortage
        ));

        if applied > 0 then
            applied_rows := applied_rows || jsonb_build_array(jsonb_build_object(
                'brand', coalesce(trim(source_row->>'brand'), ''),
                'material', coalesce(trim(source_row->>'material'), ''),
                'color', coalesce(trim(source_row->>'color'), ''),
                'size', upper(coalesce(trim(source_row->>'size'), '')),
                'quantity_change', -applied,
                'movement_date', p_movement_date,
                'reason', '仓库每日出货'
            ));
        end if;
    end loop;

    if jsonb_array_length(applied_rows) > 0 then
        inventory_batch_id := public.apply_inventory_adjustment_batch(
            p_department, p_category, applied_rows,
            gen_random_uuid(), effective_user
        );
        update public.inventory_movements
        set source_type = 'daily_outbound'
        where batch_id = inventory_batch_id;
    end if;

    insert into public.inventory_daily_outbound_revisions (
        daily_outbound_batch_id, revision_number, action,
        inventory_batch_id, reversal_inventory_batch_id,
        requested_total, applied_total, shortage_total,
        note, created_by
    ) values (
        logical_batch.id, next_revision,
        case when next_revision = 1 then 'create' else 'edit' end,
        inventory_batch_id, reversal_batch_id,
        requested_total, applied_total, shortage_total,
        p_note, effective_user
    ) returning id into new_revision_id;

    insert into public.inventory_daily_outbound_lines (
        revision_id, brand, material, color, size,
        requested_quantity, applied_quantity, shortage_quantity
    )
    select
        new_revision_id,
        value->>'brand', value->>'material', value->>'color', value->>'size',
        (value->>'requested_quantity')::integer,
        (value->>'applied_quantity')::integer,
        (value->>'shortage_quantity')::integer
    from jsonb_array_elements(result_lines);

    update public.inventory_daily_outbound_batches
    set current_revision = next_revision,
        status = 'active',
        updated_by = effective_user,
        updated_at = now()
    where id = logical_batch.id;

    return jsonb_build_object(
        'daily_outbound_batch_id', logical_batch.id,
        'revision_id', new_revision_id,
        'revision_number', next_revision,
        'inventory_batch_id', inventory_batch_id,
        'requested_total', requested_total,
        'applied_total', applied_total,
        'shortage_total', shortage_total
    );
end;
$$;

grant select, insert, update on public.inventory_daily_outbound_batches
to service_role;
grant select, insert on public.inventory_daily_outbound_revisions
to service_role;
grant select, insert on public.inventory_daily_outbound_lines
to service_role;
grant execute on function public.save_inventory_daily_outbound_revision(
    text, text, date, jsonb, text, uuid, text
) to service_role;

commit;
notify pgrst, 'reload schema';
