create or replace function public.get_erp_api_credential_status(
    p_platform text
)
returns table (
    platform text,
    status text,
    token_fingerprint text,
    last_refreshed_at timestamptz,
    last_used_at timestamptz,
    updated_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        c.platform,
        c.status,
        c.token_fingerprint,
        c.last_refreshed_at,
        c.last_used_at,
        c.updated_at
    from public.erp_api_credentials c
    where c.platform = p_platform
    limit 1;
$$;

grant execute on function public.get_erp_api_credential_status(text)
to anon, authenticated, service_role;

notify pgrst, 'reload schema';
