alter table public.barcode_scans
add column if not exists multiple_count integer;

create index if not exists idx_barcode_scans_multiple_date
on public.barcode_scans (scanned_at)
where multiple_count is null;

create index if not exists idx_barcode_scans_scanned_at_barcode
on public.barcode_scans (scanned_at, barcode);

create or replace function public.refresh_barcode_multiple_counts_for_format(
    target_date date,
    target_format text default null
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    start_at timestamptz;
    end_at timestamptz;
    refreshed_rows integer;
begin
    start_at := target_date::timestamp at time zone 'America/New_York';
    end_at := (target_date + interval '1 day')::timestamp
        at time zone 'America/New_York';

    if not exists (
        select 1
        from public.barcode_scans
        where multiple_count is null
          and scanned_at >= start_at
          and scanned_at < end_at
          and (
              ((target_format is null or upper(trim(target_format)) = 'SCGD')
                and barcode like 'SCGD-%'
                and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$')
              or ((target_format is null or upper(trim(target_format)) = 'S2B')
                and length(barcode) between 8 and 12
                and barcode ~ '^[A-Z0-9]{6}-[0-9]+$')
          )
    ) then
        return 0;
    end if;

    drop table if exists pg_temp.multiple_parsed_rows;
    create temp table multiple_parsed_rows on commit drop as
    select
        id,
        multiple_count,
        case
            when barcode like 'SCGD-%'
            then 'SCGD:' || substring(
                barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$'
            )
            else 'S2B:' || substring(
                barcode from '^([A-Z0-9]{6})-[0-9]+$'
            )
        end as order_key,
        case
            when barcode like 'SCGD-%'
            then substring(
                barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$'
            )::integer
            else substring(
                barcode from '^[A-Z0-9]{6}-([0-9]+)$'
            )::integer
        end as item_no
    from public.barcode_scans
    where scanned_at >= start_at
      and scanned_at < end_at
      and (
          (
              (target_format is null or upper(trim(target_format)) = 'SCGD')
              and barcode like 'SCGD-%'
              and barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$'
          )
          or (
              (target_format is null or upper(trim(target_format)) = 'S2B')
              and length(barcode) between 8 and 12
              and barcode ~ '^[A-Z0-9]{6}-[0-9]+$'
          )
      );

    create index on pg_temp.multiple_parsed_rows (order_key);
    analyze pg_temp.multiple_parsed_rows;

    with target_counts as materialized (
        select
            order_key,
            count(distinct item_no)::integer as multiple_count
        from pg_temp.multiple_parsed_rows
        group by order_key
        having bool_or(multiple_count is null)
    ), updated_rows as (
        update public.barcode_scans scan
        set multiple_count = target.multiple_count
        from pg_temp.multiple_parsed_rows parsed
        join target_counts target using (order_key)
        where scan.id = parsed.id
          and scan.multiple_count is distinct from target.multiple_count
        returning scan.id
    )
    select count(*)::integer into refreshed_rows
    from updated_rows;

    return refreshed_rows;
end;
$$;

create or replace function public.refresh_scgd_multiple_counts(
    target_date date
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_barcode_multiple_counts_for_format(
        target_date, 'SCGD'
    );
end;
$$;

create or replace function public.refresh_s2b_multiple_counts(
    target_date date
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_barcode_multiple_counts_for_format(
        target_date, 'S2B'
    );
end;
$$;

create or replace function public.refresh_barcode_multiple_counts(
    target_date date
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_barcode_multiple_counts_for_format(
        target_date, null
    );
end;
$$;

create or replace function public.refresh_barcode_multiple_counts()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.refresh_barcode_multiple_counts(
        (now() at time zone 'America/New_York')::date
    );
end;
$$;

revoke all on function public.refresh_barcode_multiple_counts_for_format(
    date, text
) from public;

grant execute on function public.refresh_scgd_multiple_counts(date)
    to anon, authenticated, service_role;
grant execute on function public.refresh_s2b_multiple_counts(date)
    to anon, authenticated, service_role;
grant execute on function public.refresh_barcode_multiple_counts(date)
    to anon, authenticated, service_role;
grant execute on function public.refresh_barcode_multiple_counts()
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
