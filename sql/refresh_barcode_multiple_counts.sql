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

    with target_rows as (
        select
            id,
            substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') as order_id,
            substring(barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$')::int as item_no
        from barcode_scans
        where multiple_count is null
          and scanned_at >= start_at
          and scanned_at < end_at
          and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$'
    ),
    target_orders as (
        select distinct order_id
        from target_rows
    ),
    parsed as (
        select distinct
            substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') as order_id,
            substring(barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$')::int as item_no
        from barcode_scans
        join target_orders
          on substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') = target_orders.order_id
        where scanned_at >= start_at
          and scanned_at < end_at
          and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$'
    ),
    counts as (
        select
            parsed.order_id,
            count(distinct parsed.item_no)::integer as multiple_count
        from parsed
        join target_orders on target_orders.order_id = parsed.order_id
        group by parsed.order_id
    )
    update barcode_scans b
    set multiple_count = counts.multiple_count
    from target_rows
    join counts on counts.order_id = target_rows.order_id
    where b.id = target_rows.id
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

    with target_rows as (
        select
            id,
            substring(barcode from '^([A-Z0-9]{6})-[0-9]+$') as order_id,
            substring(barcode from '^[A-Z0-9]{6}-([0-9]+)$')::int as item_no
        from barcode_scans
        where multiple_count is null
          and scanned_at >= start_at
          and scanned_at < end_at
          and barcode ~ '^[A-Z0-9]{6}-[0-9]+$'
    ),
    target_orders as (
        select distinct order_id
        from target_rows
    ),
    parsed as (
        select distinct
            substring(barcode from '^([A-Z0-9]{6})-[0-9]+$') as order_id,
            substring(barcode from '^[A-Z0-9]{6}-([0-9]+)$')::int as item_no
        from barcode_scans
        join target_orders
          on substring(barcode from '^([A-Z0-9]{6})-[0-9]+$') = target_orders.order_id
        where scanned_at >= start_at
          and scanned_at < end_at
          and barcode ~ '^[A-Z0-9]{6}-[0-9]+$'
    ),
    counts as (
        select
            parsed.order_id,
            count(distinct parsed.item_no)::integer as multiple_count
        from parsed
        join target_orders on target_orders.order_id = parsed.order_id
        group by parsed.order_id
    )
    update barcode_scans b
    set multiple_count = counts.multiple_count
    from target_rows
    join counts on counts.order_id = target_rows.order_id
    where b.id = target_rows.id
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
