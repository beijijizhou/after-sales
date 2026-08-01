create table if not exists public.inventory_snapshots (
    id uuid primary key default gen_random_uuid(),
    snapshot_batch_id uuid not null,
    snapshot_date date not null,
    department text not null default 'DTF',
    category text,
    brand text not null default '',
    material text not null default '',
    color text not null default '',
    size text not null default '',
    unit_cost numeric(10, 2) not null default 0,
    quantity integer not null default 0 check (quantity >= 0),
    created_at timestamptz not null default now()
);

create index if not exists inventory_snapshots_lookup_idx
on public.inventory_snapshots (
    snapshot_date,
    department,
    coalesce(category, ''),
    created_at desc
);

create index if not exists inventory_snapshots_batch_idx
on public.inventory_snapshots (snapshot_batch_id);

create or replace function public.create_inventory_snapshot(
    p_department text,
    p_category text,
    p_snapshot_date date
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    new_batch_id uuid := gen_random_uuid();
    recorded_at timestamptz := now();
begin
    insert into public.inventory_snapshots (
        snapshot_batch_id,
        snapshot_date,
        department,
        category,
        brand,
        material,
        color,
        size,
        unit_cost,
        quantity,
        created_at
    )
    select
        new_batch_id,
        p_snapshot_date,
        inventory_items.department,
        inventory_items.category,
        inventory_items.brand,
        inventory_items.material,
        inventory_items.color,
        inventory_items.size,
        inventory_items.unit_cost,
        inventory_items.quantity,
        recorded_at
    from public.inventory_items
    where inventory_items.department = p_department
      and (
          coalesce(p_category, '') = ''
          or coalesce(inventory_items.category, '') = p_category
      );

    return new_batch_id;
end;
$$;

create or replace function public.get_inventory_snapshot(
    p_department text,
    p_category text,
    p_snapshot_date date
)
returns table (
    department text,
    category text,
    brand text,
    material text,
    color text,
    size text,
    unit_cost numeric,
    quantity integer,
    updated_at timestamptz
)
language sql
security definer
set search_path = public
as $$
    with latest_batches as (
        select distinct on (coalesce(category, ''))
            snapshot_batch_id,
            coalesce(category, '') as category_key
        from public.inventory_snapshots
        where snapshot_date = p_snapshot_date
          and department = p_department
          and (
              coalesce(p_category, '') = ''
              or coalesce(category, '') = p_category
          )
        order by coalesce(category, ''), created_at desc
    )
    select
        snapshots.department,
        snapshots.category,
        snapshots.brand,
        snapshots.material,
        snapshots.color,
        snapshots.size,
        snapshots.unit_cost,
        snapshots.quantity,
        snapshots.created_at as updated_at
    from public.inventory_snapshots snapshots
    join latest_batches on latest_batches.snapshot_batch_id = snapshots.snapshot_batch_id
    order by snapshots.material, snapshots.color, snapshots.size;
$$;

grant select, insert on public.inventory_snapshots to anon;
grant select, insert on public.inventory_snapshots to authenticated;
grant select, insert on public.inventory_snapshots to service_role;

grant execute on function public.create_inventory_snapshot(text, text, date) to anon;
grant execute on function public.create_inventory_snapshot(text, text, date) to authenticated;
grant execute on function public.create_inventory_snapshot(text, text, date) to service_role;

grant execute on function public.get_inventory_snapshot(text, text, date) to anon;
grant execute on function public.get_inventory_snapshot(text, text, date) to authenticated;
grant execute on function public.get_inventory_snapshot(text, text, date) to service_role;

do $$
declare
    inventory_group record;
begin
    for inventory_group in
        select distinct
            department,
            category
        from public.inventory_items
    loop
        perform public.create_inventory_snapshot(
            inventory_group.department,
            inventory_group.category,
            (now() at time zone 'America/New_York')::date
        );
    end loop;
end;
$$;

notify pgrst, 'reload schema';
