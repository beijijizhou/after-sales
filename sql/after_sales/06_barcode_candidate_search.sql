begin;

drop function if exists public.search_barcode_scans_by_candidates(text[]);
drop function if exists public.search_barcode_scans_by_candidates(text[], text[]);
drop function if exists public.search_barcode_scans_by_candidates(
    text[], text[], text[]
);

create or replace function public.search_barcode_scans_by_candidates(
    p_barcodes text[],
    p_prefixes text[],
    p_embedded_keys text[],
    p_order_codes text[] default '{}'
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
       or cardinality(coalesce(p_embedded_keys, '{}')) > 5000
       or cardinality(coalesce(p_order_codes, '{}')) > 5000 then
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
    -- A LIKE whose pattern is not a constant cannot use an index, so bound
    -- the prefix with the byte-order operators of the text_pattern_ops index.
    join public.barcode_scans scan
      on term.prefix <> ''
     and scan.barcode ~>=~ term.prefix
     and scan.barcode ~<~ (
         left(term.prefix, -1)
         || chr(ascii(right(term.prefix, 1)) + 1)
     )
    union
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from public.barcode_scans scan
    where substring(
        upper(scan.barcode)
        from '(LB[0-9]{11}[A-Z][0-9]+|LB[0-9]{11})'
    ) = any(coalesce(p_embedded_keys, '{}'))
    union
    -- The two branches below repeat the partial-index predicates of
    -- 07_humbird_order_code_index.sql and 08_s2b_order_code_index.sql.
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from public.barcode_scans scan
    where scan.barcode not like 'SCGD-%'
      and upper(scan.barcode) ~ '(SCGD-|^)B[A-Z0-9]{6}(-|$)'
      and substring(
          upper(scan.barcode)
          from '(?:SCGD-|^)(B[A-Z0-9]{6})(?:-|$)'
      ) = any(coalesce(p_order_codes, '{}'))
    union
    select
        scan.barcode::text,
        scan.scanned_by::text,
        scan.scanned_at::timestamptz
    from public.barcode_scans scan
    where scan.barcode !~ '^[A-Z0-9]{6}-[0-9]+$'
      and scan.barcode not like '%SCGD-%'
      and scan.barcode ~ '[A-Za-z0-9]{6}-[0-9]+$'
      and substring(
          upper(scan.barcode)
          from '([A-Z0-9]{6})-[0-9]+$'
      ) = any(coalesce(p_order_codes, '{}'));
end;
$$;

grant execute on function public.search_barcode_scans_by_candidates(
    text[], text[], text[], text[]
)
to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
