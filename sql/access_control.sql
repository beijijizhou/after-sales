-- Access control foundation for the Streamlit app.
-- Database stores only user identity and role.
-- Role permissions are defined in utils/auth/constants.py.

alter table public.users
add column if not exists role text not null default 'visitor';

alter table public.users
add column if not exists is_active boolean not null default true;

alter table public.users
drop constraint if exists user_role_check;

alter table public.users
add constraint user_role_check
check (role in ('visitor', 'supervisor', 'warehouse', 'after_sales', 'admin'));

drop function if exists public.get_app_user_login(text);

create function public.get_app_user_login(p_username text)
returns table (
    username text,
    display_name text,
    password_hash text,
    role text,
    is_active boolean
)
language sql
stable
as $$
    select
        u.user_name as username,
        u.name as display_name,
        u.password as password_hash,
        coalesce(u.role, 'visitor') as role,
        coalesce(u.is_active, true) as is_active
    from public.users u
    where u.user_name = trim(p_username)
      and coalesce(u.is_active, true) = true
    limit 1;
$$;

grant select, insert, update on public.users to authenticated;
grant execute on function public.get_app_user_login(text) to anon;
grant execute on function public.get_app_user_login(text) to authenticated;
grant execute on function public.get_app_user_login(text) to service_role;

notify pgrst, 'reload schema';
