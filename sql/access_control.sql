-- Access control foundation for the Streamlit app.
-- The app uses its own login table instead of Supabase Auth sessions.

-- Your existing login table is named public.users.
-- The only user-level access column needed is role.
alter table public.users
add column if not exists role text not null default 'visitor';

alter table public.users
add column if not exists is_active boolean not null default true;

alter table public.users
drop constraint if exists user_role_check;

alter table public.users
add constraint user_role_check
check (role in ('visitor', 'supervisor', 'warehouse', 'after_sales', 'admin'));

create table if not exists public.app_role_permissions (
    role text primary key,
    role_label text not null,
    can_view_app boolean not null default false,
    can_register boolean not null default false,
    can_view_qa boolean not null default false,
    can_view_hotstamp boolean not null default false,
    can_view_platform boolean not null default false,
    can_view_inventory boolean not null default false,
    can_edit_inventory boolean not null default false,
    can_view_container boolean not null default false,
    can_edit_container boolean not null default false,
    can_input_after_sales boolean not null default false,
    can_view_cost boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint app_role_permissions_role_check
        check (role in ('visitor', 'supervisor', 'warehouse', 'after_sales', 'admin'))
);

insert into public.app_role_permissions (
    role,
    role_label,
    can_view_app,
    can_register,
    can_view_qa,
    can_view_hotstamp,
    can_view_platform,
    can_view_inventory,
    can_edit_inventory,
    can_view_container,
    can_edit_container,
    can_input_after_sales,
    can_view_cost
)
values
    -- 游客：不需要登录；可以看注册入口、质检、烫印、平台；不能看售后查询、库存、货柜。
    ('visitor', '游客', false, true, true, true, true, false, false, false, false, false, false),

    -- 主管：包含游客权限，并且可以看库存和货柜安排；不能看售后查询，默认不修改库存。
    ('supervisor', '主管', false, true, true, true, true, true, false, true, false, false, false),

    -- 仓库：只负责库存和货柜安排，不看售后查询、质检、烫印、平台。
    ('warehouse', '仓库', false, false, false, false, false, true, true, true, true, false, false),

    -- 售后：高级别，除成本外基本全部可以操作。
    ('after_sales', '售后', true, true, true, true, true, true, true, true, true, true, false),

    -- 管理员：所有权限，包括成本。
    ('admin', '管理员', true, true, true, true, true, true, true, true, true, true, true)
on conflict (role) do update set
    role_label = excluded.role_label,
    can_view_app = excluded.can_view_app,
    can_register = excluded.can_register,
    can_view_qa = excluded.can_view_qa,
    can_view_hotstamp = excluded.can_view_hotstamp,
    can_view_platform = excluded.can_view_platform,
    can_view_inventory = excluded.can_view_inventory,
    can_edit_inventory = excluded.can_edit_inventory,
    can_view_container = excluded.can_view_container,
    can_edit_container = excluded.can_edit_container,
    can_input_after_sales = excluded.can_input_after_sales,
    can_view_cost = excluded.can_view_cost,
    updated_at = now();

create or replace function public.get_app_user_login(p_username text)
returns table (
    username text,
    display_name text,
    password_hash text,
    role text,
    role_label text,
    is_active boolean,
    can_view_app boolean,
    can_register boolean,
    can_view_qa boolean,
    can_view_hotstamp boolean,
    can_view_platform boolean,
    can_view_inventory boolean,
    can_edit_inventory boolean,
    can_view_container boolean,
    can_edit_container boolean,
    can_input_after_sales boolean,
    can_view_cost boolean
)
language sql
stable
as $$
    select
        u.user_name as username,
        u.name as display_name,
        u.password as password_hash,
        u.role,
        p.role_label,
        u.is_active,
        p.can_view_app,
        p.can_register,
        p.can_view_qa,
        p.can_view_hotstamp,
        p.can_view_platform,
        p.can_view_inventory,
        p.can_edit_inventory,
        p.can_view_container,
        p.can_edit_container,
        p.can_input_after_sales,
        p.can_view_cost
    from public.users u
    join public.app_role_permissions p on p.role = u.role
    where u.user_name = trim(p_username)
      and u.is_active = true
    limit 1;
$$;

grant select, insert, update on public.users to authenticated;
grant select on public.app_role_permissions to authenticated;
grant execute on function public.get_app_user_login(text) to authenticated;

notify pgrst, 'reload schema';
