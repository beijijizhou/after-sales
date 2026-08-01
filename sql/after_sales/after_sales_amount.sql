alter table public.after_sales
add column if not exists amount numeric(12, 2) not null default 0;

alter table public.after_sales
add column if not exists product_type text not null default '短袖';

alter table public.after_sales
add column if not exists quantity integer not null default 1;

alter table public.after_sales
add column if not exists scanned_at timestamptz;

alter table public.after_sales
add column if not exists entered_at timestamptz;

comment on column public.after_sales.amount is '售后金额';
comment on column public.after_sales.product_type is '售后类型：选项由 Streamlit 控制';
comment on column public.after_sales.quantity is '售后件数';
comment on column public.after_sales.scanned_at is '原始条码扫描时间，也是售后发货时间';
comment on column public.after_sales.entered_at is '最后一次售后输入时间';

update public.after_sales a
set scanned_at = b.scanned_at
from public.barcode_scans b
where a.scanned_at is null
  and upper(trim(a.barcode)) = upper(trim(b.barcode));

notify pgrst, 'reload schema';
