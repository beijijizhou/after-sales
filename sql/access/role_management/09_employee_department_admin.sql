begin;

create or replace function public.update_app_user_profile_access(
    p_username text, p_role text, p_is_active boolean,
    p_departments text[], p_changed_by text
)
returns table (
    user_name text, role text, is_active boolean, departments text[]
)
language plpgsql
security definer
set search_path = public
as $$
declare
    target_employee_id text;
    current_role text;
    current_active boolean;
    current_departments text[];
    normalized_departments text[];
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
    select coalesce(array_agg(distinct upper(trim(value))), '{}')
    into normalized_departments
    from unnest(coalesce(p_departments, '{}')) value
    where nullif(trim(value), '') is not null;
    if cardinality(normalized_departments) = 0 then
        raise exception 'At least one production department is required';
    end if;
    if exists (
        select 1 from unnest(normalized_departments) code
        where not exists (
            select 1 from public.app_production_departments d
            where d.department_code = code and d.is_active
        )
    ) then
        raise exception 'Unsupported production department';
    end if;
    select u.employee_id, coalesce(u.role, 'visitor'), coalesce(u.is_active, true)
    into target_employee_id, current_role, current_active
    from public.users u
    where u.user_name = normalized_username
    for update;
    if not found then raise exception 'User not found'; end if;
    select coalesce(array_agg(d.department_code order by d.department_code), '{}')
    into current_departments
    from public.app_user_departments d
    where d.employee_id = target_employee_id;
    if normalized_username = normalized_actor and (
        current_role <> p_role or current_active <> p_is_active
    ) then
        raise exception 'Access administrator cannot change own access';
    end if;
    update public.users u
    set role = p_role, is_active = p_is_active
    where u.employee_id = target_employee_id;
    delete from public.app_user_departments d
    where d.employee_id = target_employee_id;
    insert into public.app_user_departments (
        employee_id, department_code, assigned_by
    ) select target_employee_id, code, normalized_actor
      from unnest(normalized_departments) code;
    insert into public.app_user_access_audit (
        user_name, old_role, new_role, old_is_active, new_is_active,
        old_departments, new_departments, changed_by
    ) values (
        normalized_username, current_role, p_role,
        current_active, p_is_active,
        current_departments, normalized_departments, normalized_actor
    );
    return query select normalized_username, p_role, p_is_active,
        normalized_departments;
end;
$$;

grant execute on function public.update_app_user_profile_access(
    text, text, boolean, text[], text
) to service_role;

commit;
