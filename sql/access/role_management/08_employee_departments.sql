begin;

alter table public.users
add column if not exists job_title text;

update public.users
set job_title = coalesce(nullif(trim(job_title), ''), nullif(trim(department), ''), '员工');

create unique index if not exists users_employee_id_unique_idx
on public.users (employee_id);

create table if not exists public.app_production_departments (
    department_code text primary key,
    department_name text not null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    constraint app_production_departments_code_check
        check (department_code ~ '^[A-Z0-9_]{2,16}$')
);

insert into public.app_production_departments (
    department_code, department_name, sort_order, is_active
)
values
    ('DTF', 'DTF', 10, true),
    ('UV', 'UV', 20, true),
    ('3D', '3D', 30, true)
on conflict (department_code) do update set
    department_name = excluded.department_name,
    sort_order = excluded.sort_order,
    is_active = excluded.is_active;

create table if not exists public.app_user_departments (
    employee_id text not null
        references public.users(employee_id) on update cascade on delete cascade,
    department_code text not null
        references public.app_production_departments(department_code),
    assigned_by text not null default 'migration',
    assigned_at timestamptz not null default now(),
    primary key (employee_id, department_code)
);

insert into public.app_user_departments (employee_id, department_code)
select u.employee_id, 'DTF'
from public.users u
where nullif(trim(u.employee_id), '') is not null
  and not exists (
      select 1 from public.app_user_departments existing
      where existing.employee_id = u.employee_id
  )
on conflict do nothing;

alter table public.app_user_access_audit
add column if not exists old_departments text[] not null default '{}';

alter table public.app_user_access_audit
add column if not exists new_departments text[] not null default '{}';

grant select on public.app_production_departments to service_role;
grant select on public.app_user_departments to service_role;

commit;

notify pgrst, 'reload schema';
