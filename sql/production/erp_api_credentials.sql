create table if not exists public.erp_api_credentials (
    platform text primary key,
    encrypted_token text not null,
    token_fingerprint text not null,
    status text not null default 'active'
        check (status in ('active', 'expired', 'error')),
    last_refreshed_at timestamptz,
    last_used_at timestamptz,
    expires_at timestamptz,
    last_error text,
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.erp_api_credentials enable row level security;

revoke all on public.erp_api_credentials from anon, authenticated;
grant select, insert, update on public.erp_api_credentials to service_role;

create index if not exists idx_erp_api_credentials_status
on public.erp_api_credentials (status, updated_at desc);

notify pgrst, 'reload schema';
