begin;

drop function if exists public.get_app_user_login(text);
create function public.get_app_user_login(p_username text)
returns table (
    username text,
    display_name text,
    password_hash text,
    role text,
    role_label text,
    is_active boolean,
    permissions jsonb
)
language sql
stable
security definer
set search_path = public
as $$
    select
        u.user_name,
        u.name,
        u.password,
        coalesce(u.role, 'visitor'),
        coalesce(r.role_name, u.role, '游客'),
        coalesce(u.is_active, true),
        coalesce((
            select jsonb_agg(rp.permission_key order by rp.permission_key)
            from public.app_role_permissions rp
            where rp.role_key = coalesce(u.role, 'visitor')
        ), '[]'::jsonb)
    from public.users u
    left join public.app_roles r on r.role_key = u.role
    where u.user_name = trim(p_username)
      and coalesce(u.is_active, true) = true
    limit 1;
$$;

grant execute on function public.get_app_user_login(text)
    to anon, authenticated, service_role;
grant select on public.app_permissions to service_role;
grant select on public.app_roles to service_role;
grant select on public.app_role_permissions to service_role;
grant select on public.app_user_access_audit to service_role;
grant select on public.app_role_change_audit to service_role;

commit;

notify pgrst, 'reload schema';
