begin;

create extension if not exists pgcrypto;

create table if not exists public.inventory_reclassification_batches (
    id uuid primary key default gen_random_uuid(),
    batch_key text not null,
    business_date date not null,
    department text not null,
    category text,
    source_scope text not null,
    target_scope text not null,
    reason text not null,
    total_quantity integer not null check (total_quantity >= 0),
    status text not null default 'completed',
    created_by text not null default 'system',
    created_at timestamptz not null default now(),
    reversed_at timestamptz,
    reversed_by text,
    constraint inventory_reclassification_batches_key_required
        check (trim(batch_key) <> ''),
    constraint inventory_reclassification_batches_status_check
        check (status in ('completed', 'reversed'))
);

create unique index if not exists inventory_reclassification_batches_key_unique
on public.inventory_reclassification_batches (batch_key);

create index if not exists inventory_reclassification_batches_date_idx
on public.inventory_reclassification_batches (business_date desc, created_at desc);

create table if not exists public.inventory_reclassification_lines (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null
        references public.inventory_reclassification_batches(id) on delete restrict,
    source_item_id uuid not null
        references public.inventory_items(id) on delete restrict,
    target_item_id uuid not null
        references public.inventory_items(id) on delete restrict,
    material text not null,
    color text not null,
    size text not null,
    source_brand text not null,
    target_brand text not null,
    quantity integer not null check (quantity > 0),
    source_quantity_before integer not null,
    source_quantity_after integer not null,
    target_quantity_before integer not null,
    target_quantity_after integer not null,
    created_at timestamptz not null default now(),
    unique (batch_id, source_item_id, target_item_id)
);

create index if not exists inventory_reclassification_lines_batch_idx
on public.inventory_reclassification_lines (batch_id);

grant select on public.inventory_reclassification_batches,
    public.inventory_reclassification_lines
to anon, authenticated, service_role;

grant insert, update on public.inventory_reclassification_batches,
    public.inventory_reclassification_lines
to authenticated, service_role;

commit;

notify pgrst, 'reload schema';
