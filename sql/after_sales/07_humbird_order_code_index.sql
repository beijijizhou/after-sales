-- Malformed Humbird scans only (leading junk, lower case, missing SCGD-).
-- Clean SCGD-... rows are served by the anchored prefix index instead.
create index concurrently if not exists idx_barcode_scans_humbird_order_code
on public.barcode_scans ((
    substring(
        upper(barcode)
        from '(?:SCGD-|^)(B[A-Z0-9]{6})(?:-|$)'
    )
))
where barcode not like 'SCGD-%'
  and upper(barcode) ~ '(SCGD-|^)B[A-Z0-9]{6}(-|$)';
