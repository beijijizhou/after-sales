begin;

create or replace function public.update_app_user_access(
    p_username text,
    p_role text,
    p_is_active boolean,
    p_changed_by text
)
returns table (user_name text, role text, is_active boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
    current_role text;
    current_active boolean;
    normalized_username text := trim(p_username);
    normalized_actor text := trim(p_changed_by);
begin
    if not public.app_actor_can_manage_access(normalized_actor) then
        raise exception 'Only an access administrator can change access';
    end if;
    if not exists (
        select 1 from public.app_roles r where r.role_key = p_role
    ) then
        raise exception 'Unsupported role';
    end if;

    select coalesce(u.role, 'visitor'), coalesce(u.is_active, true)
    into current_role, current_active
    from public.users u
    where u.user_name = normalized_username
    for update;
    if not found then
        raise exception 'User not found';
    end if;
    if current_role = p_role and current_active = p_is_active then
        return query select normalized_username, current_role, current_active;
        return;
    end if;
    if normalized_username = normalized_actor then
        raise exception 'Access administrator cannot change own access';
    end if;

    update public.users u
    set role = p_role, is_active = p_is_active
    where u.user_name = normalized_username;

    insert into public.app_user_access_audit (
        user_name, old_role, new_role, old_is_active, new_is_active, changed_by
    ) values (
        normalized_username, current_role, p_role,
        current_active, p_is_active, normalized_actor
    );
    return query select normalized_username, p_role, p_is_active;
end;
$$;

revoke all on function public.update_app_user_access(text, text, boolean, text)
    from public, anon, authenticated;
grant execute on function public.update_app_user_access(text, text, boolean, text)
    to service_role;

commit;
