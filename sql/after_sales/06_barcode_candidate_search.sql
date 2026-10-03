begin;

drop function if exists public.search_barcode_scans_by_candidates(text[]);
drop function if exists public.search_barcode_scans_by_candidates(text[], text[]);

create or replace function public.search_barcode_scans_by_candidates(
    p_barcodes text[],
    p_prefixes text[],
    p_embedded_keys text[]
)
returns table (
    barcode text,
    scanned_by text,
    scanned_at timestamptz
)
language plpgsql
stable
security invoker
set search_path = public
as $$
begin
    if cardinality(coalesce(p_barcodes, '{}')) > 5000
       or cardinality(coalesce(p_prefixes, '{}')) > 5000
       or cardinality(coalesce(p_embedded_keys, '{}')) > 5000 then
        raise exception 'Too many barcode search terms';
    end if;

    return query
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from public.barcode_scans scan
    where scan.barcode = any(coalesce(p_barcodes, '{}'))
    union
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from unnest(coalesce(p_prefixes, '{}')) as term(prefix)
    join public.barcode_scans scan
      on scan.barcode like term.prefix || '%'
    union
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from public.barcode_scans scan
    where substring(
        upper(scan.barcode)
        from '(LB[0-9]{11}[A-Z][0-9]+|LB[0-9]{11})'
    ) = any(coalesce(p_embedded_keys, '{}'));
end;
$$;

grant execute on function public.search_barcode_scans_by_candidates(
    text[], text[], text[]
)
to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
