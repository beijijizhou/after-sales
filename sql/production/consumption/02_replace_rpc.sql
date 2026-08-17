begin;

create or replace function public.replace_platform_daily_consumption(
    p_department text,
    p_category text,
    p_platform text,
    p_start_date date,
    p_end_date date,
    p_rows jsonb,
    p_source text default 'ERP/API',
    p_operator text default 'system'
)
returns table (saved_rows integer, saved_quantity bigint, batch_id uuid)
language plpgsql security definer set search_path = public
as $$
declare
    v_rows integer := 0;
    v_quantity bigint := 0;
    v_batch_id uuid;
begin
    if trim(coalesce(p_platform, '')) = '' then
        raise exception '平台不能为空';
    end if;
    if trim(coalesce(p_department, '')) = ''
       or trim(coalesce(p_category, '')) = '' then
        raise exception '部门和品类不能为空';
    end if;
    if p_start_date is null or p_end_date is null
       or p_end_date < p_start_date
       or p_end_date - p_start_date > 31 then
        raise exception '保存日期范围无效或超过 31 天';
    end if;

    delete from public.production_platform_daily_consumption
    where platform = trim(p_platform)
      and business_date between p_start_date and p_end_date
      and department = trim(p_department)
      and category = trim(p_category);

    insert into public.production_platform_daily_consumption (
        business_date, department, category, platform, color, size,
        quantity, record_count, source, fetched_at
    )
    select row.business_date, trim(p_department), trim(p_category),
        trim(p_platform),
        trim(row.color), upper(trim(row.size)),
        greatest(coalesce(row.quantity, 0), 0),
        greatest(coalesce(row.record_count, 0), 0),
        coalesce(nullif(trim(p_source), ''), 'ERP/API'), now()
    from jsonb_to_recordset(coalesce(p_rows, '[]'::jsonb)) as row(
        business_date date, color text, size text,
        quantity integer, record_count integer
    )
    where row.business_date between p_start_date and p_end_date
      and trim(coalesce(row.color, '')) <> ''
      and trim(coalesce(row.size, '')) <> ''
    on conflict (
        business_date, department, category, platform, color, size
    ) do update set
        quantity = excluded.quantity,
        record_count = excluded.record_count,
        source = excluded.source,
        fetched_at = now();

    get diagnostics v_rows = row_count;
    select coalesce(sum(quantity), 0) into v_quantity
    from public.production_platform_daily_consumption
    where platform = trim(p_platform)
      and business_date between p_start_date and p_end_date
      and department = trim(p_department)
      and category = trim(p_category);

    insert into public.production_consumption_sync_batches (
        department, category, platform, start_date, end_date,
        source, row_count,
        total_quantity, operator, status
    ) values (
        trim(p_department), trim(p_category), trim(p_platform),
        p_start_date, p_end_date,
        coalesce(nullif(trim(p_source), ''), 'ERP/API'),
        v_rows, v_quantity, coalesce(nullif(trim(p_operator), ''), 'system'),
        'completed'
    ) returning id into v_batch_id;

    return query select v_rows, v_quantity, v_batch_id;
end;
$$;

grant execute on function public.replace_platform_daily_consumption(
    text, text, text, date, date, jsonb, text, text
) to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
