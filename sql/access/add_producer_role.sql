alter table public.users
drop constraint if exists user_role_check;

alter table public.users
add constraint user_role_check
check (
    role in (
        'visitor', 'supervisor', 'producer', 'warehouse',
        'after_sales', 'finance', 'admin'
    )
);

update public.users
set role = 'producer'
where lower(trim(user_name)) = 'damo';

notify pgrst, 'reload schema';
