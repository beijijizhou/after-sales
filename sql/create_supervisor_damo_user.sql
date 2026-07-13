-- Create or update the supervisor login account.
-- Username: damo
-- Password: damo

alter table public.users
add column if not exists role text not null default 'visitor';

alter table public.users
add column if not exists is_active boolean not null default true;

update public.users
set
    name = coalesce(nullif(name, ''), 'damo'),
    department = coalesce(nullif(department, ''), '主管'),
    employee_id = coalesce(nullif(employee_id, ''), 'damo_id'),
    password = 'damo',
    role = 'supervisor',
    is_active = true
where user_name = 'damo';

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
    'damo',
    'damo',
    'damo_id',
    '主管',
    'damo',
    'supervisor',
    true
where not exists (
    select 1
    from public.users
    where user_name = 'damo'
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
where user_name = 'damo';
