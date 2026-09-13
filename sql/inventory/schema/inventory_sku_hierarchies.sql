-- Prerequisite: inventory_master_data.sql. No SKU or inventory rows are rewritten.
-- Navigation metadata is independent of inventory_items and financial history.
begin;
create table if not exists public.inventory_sku_hierarchies (
    department text not null,
    category text not null,
    levels jsonb not null,
    version integer not null default 1,
    changed_by text not null,
    changed_at timestamptz not null default now(),
    primary key (department, category)
);
create table if not exists public.inventory_sku_hierarchy_history (
    id bigint generated always as identity primary key,
    department text not null,
    category text not null,
    version integer not null,
    old_levels jsonb,
    new_levels jsonb not null,
    changed_by text not null,
    changed_at timestamptz not null default now()
);
alter table public.inventory_sku_hierarchies enable row level security;
alter table public.inventory_sku_hierarchy_history enable row level security;
create or replace function public.save_inventory_sku_hierarchy(
    p_department text, p_category text, p_levels jsonb,
    p_expected_version integer, p_operator text
) returns integer language plpgsql security invoker set search_path = public as $$
declare old_row public.inventory_sku_hierarchies%rowtype; next_version integer;
begin
    if not exists (select 1 from public.inventory_categories c
        join public.inventory_departments d on d.id=c.department_id
        where d.code=p_department and c.name=p_category) then
        raise exception 'Unknown department/category';
    end if;
    if nullif(trim(p_operator), '') is null or p_operator = 'system' then
        raise exception 'Human operator is required';
    end if;
    if jsonb_typeof(p_levels) <> 'array' or jsonb_array_length(p_levels) = 0 then
        raise exception 'Nonempty hierarchy levels are required';
    end if;
    if exists (select 1 from jsonb_array_elements(p_levels) level
        where nullif(trim(level->>'field'), '') is null
           or nullif(trim(level->>'label'), '') is null) then
        raise exception 'Field and label are required';
    end if;
    if (select count(*) <> count(distinct level->>'field')
        from jsonb_array_elements(p_levels) level) then
        raise exception 'Duplicate hierarchy fields';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_department || ':' || p_category, 0));
    select * into old_row from public.inventory_sku_hierarchies
      where department = p_department and category = p_category for update;
    if coalesce(old_row.version, 0) <> p_expected_version then
        raise exception 'Hierarchy changed; reload before saving';
    end if;
    next_version := coalesce(old_row.version, 0) + 1;
    insert into public.inventory_sku_hierarchies values
      (p_department,p_category,p_levels,next_version,p_operator,now())
    on conflict (department,category) do update set
      levels=excluded.levels, version=excluded.version,
      changed_by=excluded.changed_by, changed_at=excluded.changed_at;
    insert into public.inventory_sku_hierarchy_history
      (department,category,version,old_levels,new_levels,changed_by)
      values(p_department,p_category,next_version,old_row.levels,p_levels,p_operator);
    return next_version;
end $$;
revoke all on function public.save_inventory_sku_hierarchy(text,text,jsonb,integer,text) from public,anon,authenticated;
grant execute on function public.save_inventory_sku_hierarchy(text,text,jsonb,integer,text) to service_role;
grant select,insert,update on public.inventory_sku_hierarchies to service_role;
grant select,insert on public.inventory_sku_hierarchy_history to service_role;
grant usage,select on sequence public.inventory_sku_hierarchy_history_id_seq to service_role;
commit;
