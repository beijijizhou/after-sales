begin;

update public.app_permissions
set permission_name = '管理员工资料及在离职',
    description = '查看完整员工名单，调整岗位/生产部门并办理离职或恢复在职'
where permission_key = 'can_manage_people';

create table if not exists public.app_employee_profile_audit (
    id uuid primary key default gen_random_uuid(),
    employee_id text not null references public.users(employee_id),
    employee_name text not null,
    old_job_title text not null,
    new_job_title text not null,
    old_departments text[] not null,
    new_departments text[] not null,
    changed_by text not null,
    changed_at timestamptz not null default now(),
    constraint app_employee_profile_changed_check check (
        old_job_title <> new_job_title
        or old_departments <> new_departments
    ),
    constraint app_employee_profile_departments_check check (
        cardinality(new_departments) > 0
    )
);

create index if not exists app_employee_profile_audit_employee_idx
on public.app_employee_profile_audit (employee_id, changed_at desc);

create or replace function public.update_employee_profile(
    p_employee_id text,
    p_job_title text,
    p_departments text[],
    p_changed_by text
)
returns table (
    employee_id text, employee_name text, job_title text, departments text[]
)
language plpgsql
security definer
set search_path = public
as $$
declare
    normalized_employee_id text := trim(p_employee_id);
    normalized_job_title text := trim(p_job_title);
    normalized_actor text := trim(p_changed_by);
    normalized_departments text[];
    target_name text;
    previous_job_title text;
    previous_departments text[];
begin
    if not exists (
        select 1
        from public.users actor
        join public.app_role_permissions rp on rp.role_key = actor.role
        where actor.user_name = normalized_actor
          and coalesce(actor.is_active, true)
          and rp.permission_key = 'can_manage_people'
    ) then
        raise exception 'Only a people administrator can change employee profile';
    end if;
    if normalized_job_title = '' then
        raise exception 'Job title is required';
    end if;
    select coalesce(array_agg(
        distinct upper(trim(value)) order by upper(trim(value))
    ), '{}')
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

    select u.name,
           coalesce(nullif(trim(u.job_title), ''), nullif(trim(u.department), ''), '员工')
    into target_name, previous_job_title
    from public.users u
    where u.employee_id = normalized_employee_id
    for update;
    if not found then
        raise exception 'Employee not found';
    end if;
    select coalesce(array_agg(d.department_code order by d.department_code), '{}')
    into previous_departments
    from public.app_user_departments d
    where d.employee_id = normalized_employee_id;
    if previous_job_title = normalized_job_title
       and previous_departments = normalized_departments then
        raise exception 'Employee profile has not changed';
    end if;

    update public.users u
    set job_title = normalized_job_title,
        department = normalized_job_title
    where u.employee_id = normalized_employee_id;
    delete from public.app_user_departments d
    where d.employee_id = normalized_employee_id;
    insert into public.app_user_departments (
        employee_id, department_code, assigned_by
    ) select normalized_employee_id, code, normalized_actor
      from unnest(normalized_departments) code;
    insert into public.app_employee_profile_audit (
        employee_id, employee_name, old_job_title, new_job_title,
        old_departments, new_departments, changed_by
    ) values (
        normalized_employee_id, target_name,
        previous_job_title, normalized_job_title,
        previous_departments, normalized_departments, normalized_actor
    );
    return query select normalized_employee_id, target_name,
        normalized_job_title, normalized_departments;
end;
$$;

grant select on public.app_employee_profile_audit to service_role;
grant execute on function public.update_employee_profile(
    text, text, text[], text
) to service_role;

commit;

notify pgrst, 'reload schema';
