-- Malformed S2B scans only (leading junk or lower case before XXXXXX-N).
-- Clean XXXXXX-N rows are served by the anchored prefix index instead.
create index concurrently if not exists idx_barcode_scans_s2b_order_code
on public.barcode_scans ((
    substring(
        upper(barcode)
        from '([A-Z0-9]{6})-[0-9]+$'
    )
))
where barcode !~ '^[A-Z0-9]{6}-[0-9]+$'
  and barcode not like '%SCGD-%'
  and barcode ~ '[A-Za-z0-9]{6}-[0-9]+$';
