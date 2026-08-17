begin;

create extension if not exists pgcrypto;

create or replace function public.register_employee_account(
    p_name text,
    p_job_title text,
    p_departments text[],
    p_username text default null,
    p_password text default null,
    p_role text default 'visitor'
)
returns table (employee_id text, departments jsonb)
language plpgsql security definer set search_path = public, extensions
as $$
declare
    v_name text := trim(p_name);
    v_job_title text := trim(p_job_title);
    v_username text := nullif(trim(coalesce(p_username, '')), '');
    v_employee_id text;
    v_departments text[];
begin
    if v_name = '' or v_job_title = '' then
        raise exception '姓名和岗位不能为空';
    end if;
    if v_username is not null and coalesce(p_password, '') = '' then
        raise exception '登录账号必须设置密码';
    end if;
    if not exists (select 1 from public.app_roles where role_key = p_role) then
        raise exception '无效角色';
    end if;

    select array_agg(distinct upper(trim(value)))
      into v_departments
      from unnest(coalesce(p_departments, '{}'::text[])) value;
    if coalesce(cardinality(v_departments), 0) = 0
       or exists (
           select 1 from unnest(v_departments) code
           where not exists (
               select 1 from public.app_production_departments d
               where d.department_code = code and d.is_active
           )
       ) then
        raise exception '员工至少需要一个有效生产部门';
    end if;

    v_employee_id := coalesce(v_username, v_name) || '_id';
    insert into public.users (
        name, user_name, password, department, job_title,
        employee_id, role, is_active
    ) values (
        v_name, v_username,
        case when v_username is null then 'N/A'
             else crypt(p_password, gen_salt('bf', 12)) end,
        v_job_title, v_job_title, v_employee_id, p_role, true
    );

    insert into public.app_user_departments (
        employee_id, department_code, assigned_by
    )
    select v_employee_id, code, coalesce(v_username, 'registration')
    from unnest(v_departments) code;

    return query select v_employee_id, to_jsonb(v_departments);
end;
$$;

create or replace function public.authenticate_qa_employee(
    p_login text, p_password text
)
returns table (
    name text, user_name text, employee_id text, role text,
    is_active boolean, job_title text, departments jsonb
)
language sql stable security definer set search_path = public, extensions
as $$
    select u.name, u.user_name, u.employee_id, coalesce(u.role, 'visitor'),
        coalesce(u.is_active, true),
        coalesce(nullif(u.job_title, ''), nullif(u.department, ''), '员工'),
        coalesce((select jsonb_agg(ud.department_code order by d.sort_order)
            from public.app_user_departments ud
            join public.app_production_departments d
              on d.department_code = ud.department_code
            where ud.employee_id = u.employee_id and d.is_active),
            '["DTF"]'::jsonb)
    from public.users u
    where (u.name = trim(p_login) or u.user_name = trim(p_login))
      and coalesce(u.is_active, true)
      and (
          u.password = p_password
          or (u.password like '$2%' and crypt(p_password, u.password) = u.password)
      )
    limit 1;
$$;

grant execute on function public.register_employee_account(
    text, text, text[], text, text, text
) to anon, authenticated, service_role;
grant execute on function public.authenticate_qa_employee(text, text)
    to anon, authenticated, service_role;

commit;

notify pgrst, 'reload schema';
