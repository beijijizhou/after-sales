create table if not exists public.s2b_batch_metadata (
    account text not null,
    batch_number text not null,
    source_total integer not null,
    records jsonb not null default '[]'::jsonb,
    summary jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    expires_at timestamptz not null,
    last_error text,
    primary key (account, batch_number),
    check (batch_number ~ '^[A-Z0-9]{12}$')
);

alter table public.s2b_batch_metadata enable row level security;

revoke all on public.s2b_batch_metadata from anon, authenticated;
grant select, insert, update on public.s2b_batch_metadata to service_role;

create index if not exists idx_s2b_batch_metadata_expiry
on public.s2b_batch_metadata (expires_at desc);

notify pgrst, 'reload schema';
