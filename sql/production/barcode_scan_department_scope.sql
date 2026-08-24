alter table public.barcode_scans
add column if not exists production_department text not null default 'DTF';

create index if not exists idx_barcode_scans_department_date
on public.barcode_scans (production_department, scanned_at);

create or replace function public.get_today_barcode_count_by_user(
    p_user text,
    p_department text default null
)
returns integer
language sql
stable
security definer
set search_path = public
as $$
    select count(distinct barcode)::integer
    from public.barcode_scans
    where scanned_by = p_user
      and coalesce(production_department, 'DTF') =
          coalesce(nullif(upper(trim(p_department)), ''), 'DTF')
      and date(scanned_at at time zone 'America/New_York')
          = date(now() at time zone 'America/New_York');
$$;

create or replace function public.get_daily_qa_person_platform_summary(
    target_date date,
    snapshot_at timestamptz default null,
    p_department text default null
)
returns table (
    person text,
    platform text,
    production_department text,
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
        coalesce(production_department, 'DTF') as production_department,
        count(*) as scan_count,
        count(*) filter (
            where coalesce(multiple_count, 1) > 1
        ) as multiple_order_count,
        min(scanned_at) as first_scan_at,
        max(scanned_at) as last_scan_at
    from public.barcode_scans
    where scanned_by is not null
      and trim(scanned_by) <> ''
      and coalesce(production_department, 'DTF') =
          coalesce(nullif(upper(trim(p_department)), ''), 'DTF')
      and scanned_at >= (
          target_date::timestamp at time zone 'America/New_York'
      )
      and scanned_at < least(
          (target_date + interval '1 day')::timestamp
              at time zone 'America/New_York',
          coalesce(
              snapshot_at,
              (target_date + interval '1 day')::timestamp
                  at time zone 'America/New_York'
          )
      )
    group by person, platform, production_department
    order by person, platform;
$$;

create or replace function public.get_daily_qa_hourly_person_client_summary(
    target_date date,
    snapshot_at timestamptz default null,
    p_department text default null
)
returns table (
    hour_start_at timestamptz,
    person text,
    production_department text,
    haloo_count bigint,
    other_count bigint,
    total_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    select
        date_trunc(
            'hour', scanned_at at time zone 'America/New_York'
        ) at time zone 'America/New_York' as hour_start_at,
        trim(scanned_by) as person,
        coalesce(production_department, 'DTF') as production_department,
        count(*) filter (
            where lower(coalesce(trim(platform), '')) = 'haloo'
        ) as haloo_count,
        count(*) filter (
            where lower(coalesce(trim(platform), '')) <> 'haloo'
        ) as other_count,
        count(*) as total_count
    from public.barcode_scans
    where scanned_by is not null
      and trim(scanned_by) <> ''
      and coalesce(production_department, 'DTF') =
          coalesce(nullif(upper(trim(p_department)), ''), 'DTF')
      and scanned_at >= (
          target_date::timestamp at time zone 'America/New_York'
      )
      and scanned_at < least(
          (target_date + interval '1 day')::timestamp
              at time zone 'America/New_York',
          coalesce(
              snapshot_at,
              (target_date + interval '1 day')::timestamp
                  at time zone 'America/New_York'
          )
      )
    group by hour_start_at, person, production_department
    order by hour_start_at, person;
$$;

grant execute on function public.get_today_barcode_count_by_user(
    text, text
) to anon, authenticated, service_role;
grant execute on function public.get_daily_qa_person_platform_summary(
    date, timestamptz, text
) to anon, authenticated, service_role;
grant execute on function public.get_daily_qa_hourly_person_client_summary(
    date, timestamptz, text
) to anon, authenticated, service_role;

notify pgrst, 'reload schema';

