-- Personal daily-work checklist and Andy's initial configurable task template.
-- Run once after sql/access/role_management/01_schema.sql through 06_login_and_grants.sql.

begin;

create extension if not exists pgcrypto;

create table if not exists public.personal_daily_work_tasks (
    id uuid primary key default gen_random_uuid(),
    owner_username text not null,
    section text not null,
    task_name text not null,
    task_kind text not null default 'daily',
    sort_order integer not null default 100,
    is_active boolean not null default true,
    created_by text not null default 'system',
    updated_by text not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint personal_daily_work_tasks_owner_required
        check (trim(owner_username) <> ''),
    constraint personal_daily_work_tasks_section_required
        check (trim(section) <> ''),
    constraint personal_daily_work_tasks_name_required
        check (trim(task_name) <> ''),
    constraint personal_daily_work_tasks_kind_check
        check (task_kind in ('daily', 'as_needed'))
);

create unique index if not exists personal_daily_work_task_identity
on public.personal_daily_work_tasks (
    lower(trim(owner_username)), lower(trim(section)), lower(trim(task_name))
);

create index if not exists personal_daily_work_task_owner_order
on public.personal_daily_work_tasks (owner_username, is_active, sort_order);

create table if not exists public.personal_daily_work_days (
    id uuid primary key default gen_random_uuid(),
    owner_username text not null,
    work_date date not null,
    summary text not null default '',
    blockers text not null default '',
    next_plan text not null default '',
    updated_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint personal_daily_work_days_owner_required
        check (trim(owner_username) <> ''),
    constraint personal_daily_work_days_owner_date_unique
        unique (owner_username, work_date)
);

create index if not exists personal_daily_work_days_history
on public.personal_daily_work_days (owner_username, work_date desc);

create table if not exists public.personal_daily_work_records (
    id uuid primary key default gen_random_uuid(),
    day_id uuid not null references public.personal_daily_work_days(id)
        on delete restrict,
    task_id uuid not null references public.personal_daily_work_tasks(id)
        on delete restrict,
    task_name_snapshot text not null,
    section_snapshot text not null,
    task_kind_snapshot text not null,
    status text not null default 'pending',
    note text not null default '',
    updated_by text not null,
    updated_at timestamptz not null default now(),
    constraint personal_daily_work_records_day_task_unique
        unique (day_id, task_id),
    constraint personal_daily_work_records_status_check
        check (status in ('pending', 'completed', 'not_applicable')),
    constraint personal_daily_work_records_kind_check
        check (task_kind_snapshot in ('daily', 'as_needed'))
);

create index if not exists personal_daily_work_records_day
on public.personal_daily_work_records (day_id);

create or replace function public.set_personal_daily_work_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists personal_daily_work_tasks_updated_at
on public.personal_daily_work_tasks;
create trigger personal_daily_work_tasks_updated_at
before update on public.personal_daily_work_tasks
for each row execute function public.set_personal_daily_work_updated_at();

drop trigger if exists personal_daily_work_days_updated_at
on public.personal_daily_work_days;
create trigger personal_daily_work_days_updated_at
before update on public.personal_daily_work_days
for each row execute function public.set_personal_daily_work_updated_at();

drop trigger if exists personal_daily_work_records_updated_at
on public.personal_daily_work_records;
create trigger personal_daily_work_records_updated_at
before update on public.personal_daily_work_records
for each row execute function public.set_personal_daily_work_updated_at();

grant select, insert, update on public.personal_daily_work_tasks
to anon, authenticated, service_role;
grant select, insert, update on public.personal_daily_work_days
to anon, authenticated, service_role;
grant select, insert, update on public.personal_daily_work_records
to anon, authenticated, service_role;

insert into public.app_permissions (
    permission_key, permission_name, permission_group, description, sort_order
)
values (
    'can_view_daily_work', '使用每日工作记录', '日常管理',
    '查看并维护当前登录账号自己的每日工作记录', 270
)
on conflict (permission_key) do update set
    permission_name = excluded.permission_name,
    permission_group = excluded.permission_group,
    description = excluded.description,
    sort_order = excluded.sort_order;

insert into public.app_role_permissions (role_key, permission_key)
values ('admin', 'can_view_daily_work')
on conflict do nothing;

with seed(section, task_name, task_kind, sort_order) as (
    values
    ('顶岗工作', 'UV打印岗位', 'as_needed', 10),
    ('顶岗工作', '白墨烫画岗位', 'as_needed', 20),
    ('顶岗工作', '帮忙打单', 'as_needed', 30),
    ('顶岗工作', '检查平台，确认是否清单', 'daily', 40),
    ('送货相关', 'USPS发货', 'as_needed', 50),
    ('送货相关', '拉衣服、膜、生产耗料', 'as_needed', 60),
    ('送货相关', '库存录入系统', 'daily', 70),
    ('送货相关', '表格截图发微信群', 'daily', 80),
    ('新平台对接', '工厂信息收集确认', 'as_needed', 90),
    ('新平台对接', '用户需求确认', 'as_needed', 100),
    ('新平台对接', '平台使用流程梳理', 'as_needed', 110),
    ('新平台对接', '教程分享准备', 'as_needed', 120),
    ('客户对接', '用户充值', 'as_needed', 130),
    ('客户对接', '订单确认', 'as_needed', 140),
    ('客户对接', '售后服务', 'as_needed', 150),
    ('杂活', '工厂网络问题处理', 'as_needed', 160),
    ('杂活', '人员临时调配', 'as_needed', 170),
    ('杂活', '保证工作正常运转', 'daily', 180)
)
insert into public.personal_daily_work_tasks (
    owner_username, section, task_name, task_kind, sort_order,
    created_by, updated_by
)
select 'a', section, task_name, task_kind, sort_order, 'Andy', 'Andy'
from seed
on conflict do nothing;

commit;

notify pgrst, 'reload schema';
