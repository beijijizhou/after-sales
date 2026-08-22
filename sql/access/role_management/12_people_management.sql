begin;

insert into public.app_permissions (
    permission_key, permission_name, permission_group, description, sort_order
) values (
    'can_manage_people', '管理员工资料及在离职', '系统管理',
    '查看完整员工名单，调整岗位/生产部门并办理离职或恢复在职', 265
)
on conflict (permission_key) do update set
    permission_name = excluded.permission_name,
    permission_group = excluded.permission_group,
    description = excluded.description,
    sort_order = excluded.sort_order;

update public.app_permissions
set permission_name = '新增员工'
where permission_key = 'can_register';

insert into public.app_role_permissions (role_key, permission_key)
values ('admin', 'can_manage_people')
on conflict do nothing;

create table if not exists public.app_employee_status_audit (
    id uuid primary key default gen_random_uuid(),
    employee_id text not null references public.users(employee_id),
    employee_name text not null,
    user_name text,
    old_is_active boolean not null,
    new_is_active boolean not null,
    effective_date date not null,
    reason text not null default '',
    changed_by text not null,
    changed_at timestamptz not null default now(),
    constraint app_employee_status_changed_check
        check (old_is_active <> new_is_active),
    constraint app_employee_departure_reason_check
        check (new_is_active or nullif(trim(reason), '') is not null)
);

create index if not exists app_employee_status_audit_employee_idx
on public.app_employee_status_audit (employee_id, changed_at desc);

create or replace function public.update_employee_employment_status(
    p_employee_id text,
    p_is_active boolean,
    p_effective_date date,
    p_reason text,
    p_changed_by text
)
returns table (
    employee_id text, employee_name text, is_active boolean,
    effective_date date
)
language plpgsql
security definer
set search_path = public
as $$
declare
    normalized_employee_id text := trim(p_employee_id);
    normalized_actor text := trim(p_changed_by);
    target_name text;
    target_username text;
    current_active boolean;
begin
    if not exists (
        select 1
        from public.users actor
        join public.app_role_permissions rp on rp.role_key = actor.role
        where actor.user_name = normalized_actor
          and coalesce(actor.is_active, true)
          and rp.permission_key = 'can_manage_people'
    ) then
        raise exception 'Only a people administrator can change employment status';
    end if;
    if p_effective_date is null then
        raise exception 'Effective date is required';
    end if;
    if p_effective_date > (now() at time zone 'America/New_York')::date then
        raise exception 'Effective date cannot be in the future';
    end if;
    if not p_is_active and nullif(trim(coalesce(p_reason, '')), '') is null then
        raise exception 'Departure reason is required';
    end if;

    select u.name, u.user_name, coalesce(u.is_active, true)
    into target_name, target_username, current_active
    from public.users u
    where u.employee_id = normalized_employee_id
    for update;
    if not found then
        raise exception 'Employee not found';
    end if;
    if target_username = normalized_actor then
        raise exception 'People administrator cannot change own employment status';
    end if;
    if current_active = p_is_active then
        raise exception 'Employment status has not changed';
    end if;

    update public.users u
    set is_active = p_is_active
    where u.employee_id = normalized_employee_id;

    insert into public.app_employee_status_audit (
        employee_id, employee_name, user_name,
        old_is_active, new_is_active, effective_date, reason, changed_by
    ) values (
        normalized_employee_id, target_name, target_username,
        current_active, p_is_active, p_effective_date,
        trim(coalesce(p_reason, '')), normalized_actor
    );

    return query select normalized_employee_id, target_name, p_is_active,
        p_effective_date;
end;
$$;

grant select on public.app_employee_status_audit to service_role;
grant execute on function public.update_employee_employment_status(
    text, boolean, date, text, text
) to service_role;

commit;

notify pgrst, 'reload schema';
