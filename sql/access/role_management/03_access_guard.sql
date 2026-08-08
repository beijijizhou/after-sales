begin;

create or replace function public.app_actor_can_manage_access(p_actor text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.users actor
        join public.app_role_permissions rp on rp.role_key = actor.role
        where actor.user_name = trim(p_actor)
          and coalesce(actor.is_active, true) = true
          and rp.permission_key = 'can_manage_access'
    );
$$;

revoke all on function public.app_actor_can_manage_access(text)
    from public, anon, authenticated;

commit;
