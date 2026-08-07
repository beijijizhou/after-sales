drop function if exists public.get_daily_qa_hourly_person_client_summary(
    date, timestamptz
);
drop function if exists public.get_daily_qa_hourly_person_client_summary(date);
drop function if exists public.get_daily_hotstamp_hourly_person_client_summary(
    date, timestamptz
);
drop function if exists public.get_daily_hotstamp_hourly_person_client_summary(
    date
);

create or replace function public.get_daily_qa_hourly_person_client_summary(
    target_date date,
    snapshot_at timestamptz default null
)
returns table (
    hour_start_at timestamptz,
    person text,
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
    group by hour_start_at, person
    order by hour_start_at, person;
$$;

create or replace function public.get_daily_hotstamp_hourly_person_client_summary(
    target_date date,
    snapshot_at timestamptz default null
)
returns table (
    hour_start_at timestamptz,
    person text,
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
        trim(hotstamp_by) as person,
        count(*) filter (
            where lower(coalesce(trim(platform), '')) = 'haloo'
        ) as haloo_count,
        count(*) filter (
            where lower(coalesce(trim(platform), '')) <> 'haloo'
        ) as other_count,
        count(*) as total_count
    from public.barcode_scans
    where hotstamp_by is not null
      and trim(hotstamp_by) <> ''
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
    group by hour_start_at, person
    order by hour_start_at, person;
$$;

grant execute on function public.get_daily_qa_hourly_person_client_summary(
    date, timestamptz
) to anon, authenticated, service_role;
grant execute on function public.get_daily_hotstamp_hourly_person_client_summary(
    date, timestamptz
) to anon, authenticated, service_role;

notify pgrst, 'reload schema';
