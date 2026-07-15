-- Create or update the after-sales login account.
-- Username: hy
-- Password: hy

alter table public.users
add column if not exists role text not null default 'visitor';

alter table public.users
add column if not exists is_active boolean not null default true;

update public.users
set
    name = '胡燕',
    department = coalesce(nullif(department, ''), '售后'),
    employee_id = coalesce(nullif(employee_id, ''), 'hy_id'),
    password = 'hy',
    role = 'after_sales',
    is_active = true
where user_name = 'hy';

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
    '胡燕',
    'hy',
    'hy_id',
    '售后',
    'hy',
    'after_sales',
    true
where not exists (
    select 1
    from public.users
    where user_name = 'hy'
);

notify pgrst, 'reload schema';

select
    name,
    user_name,
    employee_id,
    department,
    password,
    role,
    is_active
from public.users
where user_name = 'hy';
