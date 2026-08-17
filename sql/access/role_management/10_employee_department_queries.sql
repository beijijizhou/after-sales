begin;

drop function if exists public.get_app_user_login(text);
create function public.get_app_user_login(p_username text)
returns table (
    username text, display_name text, password_hash text, role text,
    role_label text, is_active boolean, permissions jsonb,
    job_title text, departments jsonb
)
language sql stable security definer set search_path = public
as $$
    select u.user_name, u.name, u.password, coalesce(u.role, 'visitor'),
        coalesce(r.role_name, u.role, '游客'), coalesce(u.is_active, true),
        coalesce((select jsonb_agg(rp.permission_key order by rp.permission_key)
            from public.app_role_permissions rp
            where rp.role_key = coalesce(u.role, 'visitor')), '[]'::jsonb),
        coalesce(nullif(u.job_title, ''), nullif(u.department, ''), '员工'),
        coalesce((select jsonb_agg(ud.department_code order by d.sort_order)
            from public.app_user_departments ud
            join public.app_production_departments d
              on d.department_code = ud.department_code
            where ud.employee_id = u.employee_id and d.is_active),
            '["DTF"]'::jsonb)
    from public.users u
    left join public.app_roles r on r.role_key = u.role
    where u.user_name = trim(p_username)
      and coalesce(u.is_active, true) = true
    limit 1;
$$;

create or replace function public.get_users_by_production_department(
    p_department text
)
returns table (
    name text, user_name text, employee_id text,
    job_title text, departments jsonb
)
language sql stable security definer set search_path = public
as $$
    select u.name, u.user_name, u.employee_id,
        coalesce(nullif(u.job_title, ''), nullif(u.department, ''), '员工'),
        coalesce((select jsonb_agg(all_ud.department_code order by d.sort_order)
            from public.app_user_departments all_ud
            join public.app_production_departments d
              on d.department_code = all_ud.department_code
            where all_ud.employee_id = u.employee_id), '["DTF"]'::jsonb)
    from public.users u
    join public.app_user_departments ud on ud.employee_id = u.employee_id
    where ud.department_code = upper(trim(p_department))
      and coalesce(u.is_active, true)
    order by u.name;
$$;

create or replace function public.get_employee_department_profile(
    p_employee_id text
)
returns table (employee_id text, job_title text, departments jsonb)
language sql stable security definer set search_path = public
as $$
    select u.employee_id,
        coalesce(nullif(u.job_title, ''), nullif(u.department, ''), '员工'),
        coalesce((select jsonb_agg(ud.department_code order by d.sort_order)
            from public.app_user_departments ud
            join public.app_production_departments d
              on d.department_code = ud.department_code
            where ud.employee_id = u.employee_id and d.is_active),
            '["DTF"]'::jsonb)
    from public.users u
    where u.employee_id = trim(p_employee_id)
    limit 1;
$$;

grant execute on function public.get_app_user_login(text)
    to anon, authenticated, service_role;
grant execute on function public.get_users_by_production_department(text)
    to anon, authenticated, service_role;
grant execute on function public.get_employee_department_profile(text)
    to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
