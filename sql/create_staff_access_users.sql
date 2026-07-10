-- Create or update staff access accounts.
-- Warehouse: username w, password w
-- Admin: username a, password a

alter table public.users
add column if not exists role text not null default 'visitor';

alter table public.users
add column if not exists is_active boolean not null default true;

update public.users
set
    name = coalesce(nullif(name, ''), 'w'),
    department = coalesce(nullif(department, ''), '仓库'),
    employee_id = coalesce(nullif(employee_id, ''), 'w_id'),
    password = 'w',
    role = 'warehouse',
    is_active = true
where user_name = 'w';

insert into public.users (
    name,
    user_name,
    employee_id,
    department,
    password,
    role,
    is_active
)
select
    'w',
    'w',
    'w_id',
    '仓库',
    'w',
    'warehouse',
    true
where not exists (
    select 1
    from public.users
    where user_name = 'w'
);

update public.users
set
    name = coalesce(nullif(name, ''), 'a'),
    department = coalesce(nullif(department, ''), '管理员'),
    employee_id = coalesce(nullif(employee_id, ''), 'a_id'),
    password = 'a',
    role = 'admin',
    is_active = true
where user_name = 'a';

insert into public.users (
    name,
    user_name,
    employee_id,
    department,
    password,
    role,
    is_active
)
select
    'a',
    'a',
    'a_id',
    '管理员',
    'a',
    'admin',
    true
where not exists (
    select 1
    from public.users
    where user_name = 'a'
);

select
    name,
    user_name,
    employee_id,
    department,
    password,
    role,
    is_active
from public.users
where user_name in ('w', 'a')
order by user_name;

notify pgrst, 'reload schema';
