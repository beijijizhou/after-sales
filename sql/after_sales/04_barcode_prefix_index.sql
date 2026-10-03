create index concurrently if not exists idx_barcode_scans_barcode_pattern
on public.barcode_scans (barcode text_pattern_ops);
