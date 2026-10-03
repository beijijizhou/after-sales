create index concurrently if not exists idx_barcode_scans_hansen_order_key
on public.barcode_scans ((
    substring(
        upper(barcode)
        from '(LB[0-9]{11}[A-Z][0-9]+|LB[0-9]{11})'
    )
));
