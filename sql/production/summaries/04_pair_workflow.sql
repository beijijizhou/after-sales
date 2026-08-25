drop function if exists public.get_daily_pair_platform_workflow_summary(
    date, timestamptz
);
drop function if exists public.get_daily_pair_platform_workflow_summary(date);
drop function if exists public.get_daily_pair_workflow_summary(
    date, timestamptz, text
);
drop function if exists public.get_daily_pair_workflow_summary(
    date, timestamptz
);
drop function if exists public.get_daily_pair_workflow_summary(date);

create or replace function public.get_daily_pair_workflow_summary(
    target_date date,
    snapshot_at timestamptz default null,
    p_department text default null
)
returns table (
    segment_start_at timestamptz,
    segment_end_at timestamptz,
    qa_person text,
    hotstamp_person text,
    scan_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    with ordered_rows as (
        select
            id,
            scanned_at,
            trim(scanned_by) as qa_person,
            trim(hotstamp_by) as hotstamp_person,
            lag(trim(hotstamp_by))
                over person_order as previous_hotstamp
        from public.barcode_scans
        where scanned_by is not null
          and trim(scanned_by) <> ''
          and hotstamp_by is not null
          and trim(hotstamp_by) <> ''
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
        window person_order as (
            partition by trim(scanned_by)
            order by scanned_at, id
        )
    ), marked_rows as (
        select
            *,
            case
                when previous_hotstamp is null
                  or hotstamp_person is distinct from previous_hotstamp
                then 1 else 0
            end as starts_segment
        from ordered_rows
    ), segmented_rows as (
        select
            *,
            sum(starts_segment) over (
                partition by qa_person
                order by scanned_at, id
            ) as segment_id
        from marked_rows
    )
    select
        min(scanned_at) as segment_start_at,
        max(scanned_at) as segment_end_at,
        qa_person,
        hotstamp_person,
        count(*) as scan_count
    from segmented_rows
    group by qa_person, segment_id, hotstamp_person
    order by segment_start_at, qa_person;
$$;

grant execute on function public.get_daily_pair_workflow_summary(
    date, timestamptz, text
) to anon, authenticated, service_role;

notify pgrst, 'reload schema';
