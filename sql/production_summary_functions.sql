create or replace function public.get_daily_qa_person_platform_summary(
    target_date date,
    snapshot_at timestamptz default null
)
returns table (
    person text,
    platform text,
    scan_count bigint,
    multiple_order_count bigint,
    first_scan_at timestamptz,
    last_scan_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        trim(scanned_by) as person,
        coalesce(nullif(trim(platform), ''), '未标记平台') as platform,
        count(*) as scan_count,
        count(*) filter (where coalesce(multiple_count, 1) > 1) as multiple_order_count,
        min(scanned_at) as first_scan_at,
        max(scanned_at) as last_scan_at
    from public.barcode_scans
    where scanned_by is not null
      and trim(scanned_by) <> ''
      and scanned_at >= (target_date::timestamp at time zone 'America/New_York')
      and scanned_at < least(
          ((target_date + interval '1 day')::timestamp at time zone 'America/New_York'),
          coalesce(snapshot_at, ((target_date + interval '1 day')::timestamp at time zone 'America/New_York'))
      )
    group by trim(scanned_by), coalesce(nullif(trim(platform), ''), '未标记平台')
    order by person, platform;
$$;

create or replace function public.get_daily_hotstamp_person_platform_summary(
    target_date date,
    snapshot_at timestamptz default null
)
returns table (
    person text,
    platform text,
    scan_count bigint,
    multiple_order_count bigint,
    first_scan_at timestamptz,
    last_scan_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        trim(hotstamp_by) as person,
        coalesce(nullif(trim(platform), ''), '未标记平台') as platform,
        count(*) as scan_count,
        count(*) filter (where coalesce(multiple_count, 1) > 1) as multiple_order_count,
        min(scanned_at) as first_scan_at,
        max(scanned_at) as last_scan_at
    from public.barcode_scans
    where hotstamp_by is not null
      and trim(hotstamp_by) <> ''
      and scanned_at >= (target_date::timestamp at time zone 'America/New_York')
      and scanned_at < least(
          ((target_date + interval '1 day')::timestamp at time zone 'America/New_York'),
          coalesce(snapshot_at, ((target_date + interval '1 day')::timestamp at time zone 'America/New_York'))
      )
    group by trim(hotstamp_by), coalesce(nullif(trim(platform), ''), '未标记平台')
    order by person, platform;
$$;

grant execute on function public.get_daily_qa_person_platform_summary(date, timestamptz) to anon;
grant execute on function public.get_daily_qa_person_platform_summary(date, timestamptz) to authenticated;
grant execute on function public.get_daily_qa_person_platform_summary(date, timestamptz) to service_role;

grant execute on function public.get_daily_hotstamp_person_platform_summary(date, timestamptz) to anon;
grant execute on function public.get_daily_hotstamp_person_platform_summary(date, timestamptz) to authenticated;
grant execute on function public.get_daily_hotstamp_person_platform_summary(date, timestamptz) to service_role;

notify pgrst, 'reload schema';
