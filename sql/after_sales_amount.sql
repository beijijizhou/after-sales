alter table public.after_sales
add column if not exists amount numeric(12, 2) not null default 0;

alter table public.after_sales
add column if not exists product_type text not null default '短袖';

alter table public.after_sales
add column if not exists quantity integer not null default 1;

comment on column public.after_sales.amount is '售后金额';
comment on column public.after_sales.product_type is '售后类型：选项由 Streamlit 控制';
comment on column public.after_sales.quantity is '售后件数';

notify pgrst, 'reload schema';
