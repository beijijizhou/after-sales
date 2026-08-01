drop function if exists public.get_period_qa_person_platform_summary(
    date, date, timestamptz
);

create or replace function public.get_period_qa_person_platform_summary(
    start_date date,
    end_date date,
    snapshot_at timestamptz default null
)
returns table (
    work_date date,
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
        (scanned_at at time zone 'America/New_York')::date as work_date,
        trim(scanned_by) as person,
        coalesce(
            nullif(trim(platform), ''),
            '未标记平台'
        ) as platform,
        count(*) as scan_count,
        count(*) filter (
            where coalesce(multiple_count, 1) > 1
        ) as multiple_order_count,
        min(scanned_at) as first_scan_at,
        max(scanned_at) as last_scan_at
    from public.barcode_scans
    where scanned_by is not null
      and trim(scanned_by) <> ''
      and scanned_at >= (
          start_date::timestamp at time zone 'America/New_York'
      )
      and scanned_at < least(
          (
              (end_date + interval '1 day')::timestamp
              at time zone 'America/New_York'
          ),
          coalesce(
              snapshot_at,
              (
                  (end_date + interval '1 day')::timestamp
                  at time zone 'America/New_York'
              )
          )
      )
    group by work_date, person, platform
    order by work_date, person, platform;
$$;

grant execute on function public.get_period_qa_person_platform_summary(
    date, date, timestamptz
) to anon, authenticated, service_role;

notify pgrst, 'reload schema';
