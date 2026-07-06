alter table barcode_scans
add column if not exists multiple_count integer;

create or replace function public.refresh_barcode_multiple_counts()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    with parsed as (
        select
            id,
            substring(barcode from '^SCGD-([A-Z0-9]+)-[0-9]+-[A-Z]$') as order_id,
            substring(barcode from '^SCGD-[A-Z0-9]+-([0-9]+)-[A-Z]$')::int as item_no
        from barcode_scans
        where barcode ~ '^SCGD-[A-Z0-9]+-[0-9]+-[A-Z]$'
    ),
    counts as (
        select
            order_id,
            count(distinct item_no)::integer as multiple_count
        from parsed
        group by order_id
    )
    update barcode_scans b
    set multiple_count = counts.multiple_count
    from parsed
    join counts on counts.order_id = parsed.order_id
    where b.id = parsed.id;

end;
$$;

grant execute on function public.refresh_barcode_multiple_counts() to anon;
grant execute on function public.refresh_barcode_multiple_counts() to authenticated;
grant execute on function public.refresh_barcode_multiple_counts() to service_role;

notify pgrst, 'reload schema';
