alter table barcode_scans
add column if not exists multiple_count integer;

create index if not exists idx_barcode_scans_multiple_date
on barcode_scans (scanned_at)
where multiple_count is null;

create index if not exists idx_barcode_scans_scanned_at_barcode
on barcode_scans (scanned_at, barcode);

create or replace function public.refresh_scgd_multiple_counts(target_date date)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    start_at timestamptz;
    end_at timestamptz;
begin
    start_at := target_date::timestamp at time zone 'America/New_York';
    end_at := (target_date + interval '1 day')::timestamp at time zone 'America/New_York';

    drop table if exists scgd_target_rows;
    drop table if exists scgd_target_orders;
    drop table if exists scgd_parsed_rows;

    create temp table scgd_target_rows on commit drop as
    select
        id,
        substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') as order_id,
        substring(barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$')::int as item_no
    from barcode_scans
    where multiple_count is null
      and scanned_at >= start_at
      and scanned_at < end_at
      and barcode like 'SCGD-%'
      and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$';

    if not exists (select 1 from scgd_target_rows) then
        return;
    end if;

    create index on scgd_target_rows (order_id);

    create temp table scgd_target_orders on commit drop as
    select distinct order_id
    from scgd_target_rows;

    create index on scgd_target_orders (order_id);

    create temp table scgd_parsed_rows on commit drop as
    select distinct
        substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') as order_id,
        substring(barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$')::int as item_no
    from barcode_scans
    where scanned_at >= start_at
      and scanned_at < end_at
      and barcode like 'SCGD-%'
      and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$';

    create index on scgd_parsed_rows (order_id);

    with counts as (
        select
            scgd_parsed_rows.order_id,
            count(distinct scgd_parsed_rows.item_no)::integer as multiple_count
        from scgd_parsed_rows
        join scgd_target_orders on scgd_target_orders.order_id = scgd_parsed_rows.order_id
        group by scgd_parsed_rows.order_id
    )
    update barcode_scans b
    set multiple_count = counts.multiple_count
    from scgd_target_rows
    join counts on counts.order_id = scgd_target_rows.order_id
    where b.id = scgd_target_rows.id
      and b.multiple_count is null;
end;
$$;

create or replace function public.refresh_s2b_multiple_counts(target_date date)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    start_at timestamptz;
    end_at timestamptz;
begin
    start_at := target_date::timestamp at time zone 'America/New_York';
    end_at := (target_date + interval '1 day')::timestamp at time zone 'America/New_York';

    drop table if exists s2b_target_rows;
    drop table if exists s2b_target_orders;
    drop table if exists s2b_parsed_rows;

    create temp table s2b_target_rows on commit drop as
    select
        id,
        substring(barcode from '^([A-Z0-9]{6})-[0-9]+$') as order_id,
        substring(barcode from '^[A-Z0-9]{6}-([0-9]+)$')::int as item_no
    from barcode_scans
    where multiple_count is null
      and scanned_at >= start_at
      and scanned_at < end_at
      and length(barcode) between 8 and 12
      and barcode ~ '^[A-Z0-9]{6}-[0-9]+$';

    if not exists (select 1 from s2b_target_rows) then
        return;
    end if;

    create index on s2b_target_rows (order_id);

    create temp table s2b_target_orders on commit drop as
    select distinct order_id
    from s2b_target_rows;

    create index on s2b_target_orders (order_id);

    create temp table s2b_parsed_rows on commit drop as
    select distinct
        substring(barcode from '^([A-Z0-9]{6})-[0-9]+$') as order_id,
        substring(barcode from '^[A-Z0-9]{6}-([0-9]+)$')::int as item_no
    from barcode_scans
    where scanned_at >= start_at
      and scanned_at < end_at
      and length(barcode) between 8 and 12
      and barcode ~ '^[A-Z0-9]{6}-[0-9]+$';

    create index on s2b_parsed_rows (order_id);

    with counts as (
        select
            s2b_parsed_rows.order_id,
            count(distinct s2b_parsed_rows.item_no)::integer as multiple_count
        from s2b_parsed_rows
        join s2b_target_orders on s2b_target_orders.order_id = s2b_parsed_rows.order_id
        group by s2b_parsed_rows.order_id
    )
    update barcode_scans b
    set multiple_count = counts.multiple_count
    from s2b_target_rows
    join counts on counts.order_id = s2b_target_rows.order_id
    where b.id = s2b_target_rows.id
      and b.multiple_count is null;
end;
$$;

create or replace function public.refresh_barcode_multiple_counts(target_date date)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_scgd_multiple_counts(target_date);
    perform public.refresh_s2b_multiple_counts(target_date);
end;
$$;

create or replace function public.refresh_barcode_multiple_counts()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_barcode_multiple_counts((now() at time zone 'America/New_York')::date);
end;
$$;

grant execute on function public.refresh_scgd_multiple_counts(date) to anon;
grant execute on function public.refresh_scgd_multiple_counts(date) to authenticated;
grant execute on function public.refresh_scgd_multiple_counts(date) to service_role;

grant execute on function public.refresh_s2b_multiple_counts(date) to anon;
grant execute on function public.refresh_s2b_multiple_counts(date) to authenticated;
grant execute on function public.refresh_s2b_multiple_counts(date) to service_role;

grant execute on function public.refresh_barcode_multiple_counts(date) to anon;
grant execute on function public.refresh_barcode_multiple_counts(date) to authenticated;
grant execute on function public.refresh_barcode_multiple_counts(date) to service_role;

grant execute on function public.refresh_barcode_multiple_counts() to anon;
grant execute on function public.refresh_barcode_multiple_counts() to authenticated;
grant execute on function public.refresh_barcode_multiple_counts() to service_role;

notify pgrst, 'reload schema';
