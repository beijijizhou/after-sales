begin;

insert into public.app_permissions (
    permission_key, permission_name, permission_group, description, sort_order
)
values
    ('can_view_app', '查看售后查询', '基础页面', '', 10),
    ('can_register', '新增员工', '基础页面', '', 20),
    ('can_view_qa', '查看质检', '生产与质检', '', 30),
    ('can_view_hotstamp', '查看烫印', '生产与质检', '', 40),
    ('can_view_platform', '查看平台', '生产与质检', '', 50),
    ('can_view_operation_tracking', '查看问题件追踪', '售后', '', 60),
    ('can_mark_barcode_operations', '处理问题件', '售后', '', 70),
    ('can_input_after_sales', '录入售后', '售后', '', 80),
    ('can_view_production_data', '查看生产数据', '生产与质检', '', 90),
    ('can_view_logistics', 'USPS官方API查询', '物流', '', 100),
    ('can_manage_logistics', '生产物流：ERP同步、OCR与管理', '物流', '', 110),
    ('can_view_inventory', '查看库存', '库存', '', 120),
    ('can_edit_inventory', '库存出入库', '库存', '', 130),
    ('can_manage_sku', '管理SKU', '库存', '', 140),
    ('can_view_container', '查看货柜', '库存', '', 150),
    ('can_edit_container', '修改货柜', '库存', '', 160),
    ('can_view_consumables', '查看耗材', '耗材', '', 170),
    ('can_edit_consumables', '修改耗材', '耗材', '', 180),
    ('can_manage_consumable_sku', '管理耗材SKU', '耗材', '', 190),
    ('can_report_consumables', '登记耗材', '耗材', '', 200),
    ('can_view_cost', '查看成本', '财务', '', 210),
    ('can_manage_cost', '管理成本', '财务', '', 220),
    ('can_view_finance_reports', '查看财务报表', '财务', '', 230),
    ('can_view_finance_dashboard', '查看财务页面', '财务', '', 240),
    ('can_use_image_stretch', '使用图片处理', '工具', '', 250),
    ('can_manage_access', '管理用户与角色权限', '系统管理', '', 260)
on conflict (permission_key) do update set
    permission_name = excluded.permission_name,
    permission_group = excluded.permission_group,
    description = excluded.description,
    sort_order = excluded.sort_order;

insert into public.app_roles (
    role_key, role_name, description, is_system
)
values
    ('visitor', '游客', '基础公开页面访问', true),
    ('producer', '生产人员', '生产与耗材登记', true),
    ('supervisor', '主管', '管理查看与物流查询', true),
    ('after_sales', '售后', '售后与物流操作', true),
    ('warehouse', '仓库', '库存、耗材和货柜操作', true),
    ('finance', '财务', '成本和财务报表查看', true),
    ('admin', '管理员', '系统全部权限', true)
on conflict (role_key) do nothing;

insert into public.app_roles (
    role_key, role_name, description, is_system
)
select distinct
    trim(u.role), trim(u.role), '迁移自现有用户角色', false
from public.users u
where nullif(trim(u.role), '') is not null
on conflict (role_key) do nothing;

with seeds(role_key, permission_keys) as (
    values
    ('visitor', array[
        'can_register','can_use_image_stretch','can_view_app',
        'can_view_hotstamp','can_view_operation_tracking',
        'can_view_platform','can_view_qa'
    ]::text[]),
    ('producer', array[
        'can_register','can_report_consumables','can_use_image_stretch',
        'can_view_app','can_view_consumables','can_view_container',
        'can_view_hotstamp','can_view_inventory','can_view_operation_tracking',
        'can_view_platform','can_view_production_data','can_view_qa',
        'can_manage_logistics'
    ]::text[]),
    ('supervisor', array[
        'can_mark_barcode_operations','can_register','can_use_image_stretch',
        'can_view_app','can_view_consumables','can_view_container',
        'can_view_hotstamp','can_view_inventory',
        'can_view_operation_tracking','can_view_platform',
        'can_view_production_data','can_view_qa'
    ]::text[]),
    ('after_sales', array[
        'can_edit_consumables','can_edit_container','can_edit_inventory',
        'can_input_after_sales','can_manage_consumable_sku',
        'can_manage_logistics','can_manage_sku','can_mark_barcode_operations',
        'can_register','can_use_image_stretch','can_view_app',
        'can_view_consumables','can_view_container','can_view_hotstamp',
        'can_view_inventory','can_view_logistics','can_view_operation_tracking',
        'can_view_platform','can_view_production_data','can_view_qa'
    ]::text[]),
    ('warehouse', array[
        'can_edit_consumables','can_edit_container',
        'can_manage_consumable_sku','can_manage_sku','can_use_image_stretch',
        'can_view_consumables','can_view_container','can_view_inventory'
    ]::text[]),
    ('finance', array[
        'can_view_consumables','can_view_container','can_view_cost',
        'can_view_finance_reports','can_view_inventory'
    ]::text[]),
    ('admin', array[
        'can_edit_consumables','can_edit_container','can_edit_inventory',
        'can_input_after_sales','can_manage_access','can_manage_consumable_sku',
        'can_manage_cost','can_manage_logistics','can_manage_sku',
        'can_mark_barcode_operations','can_register','can_report_consumables',
        'can_use_image_stretch','can_view_app','can_view_consumables',
        'can_view_container','can_view_cost','can_view_finance_dashboard',
        'can_view_finance_reports','can_view_hotstamp','can_view_inventory',
        'can_view_logistics','can_view_operation_tracking','can_view_platform',
        'can_view_production_data','can_view_qa'
    ]::text[])
)
insert into public.app_role_permissions (role_key, permission_key)
select seed.role_key, permission_key
from seeds seed
cross join lateral unnest(seed.permission_keys) permission_key
where not exists (
    select 1 from public.app_role_permissions existing
    where existing.role_key = seed.role_key
)
on conflict do nothing;

alter table public.users drop constraint if exists user_role_check;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'users_role_app_roles_fk'
    ) then
        alter table public.users
        add constraint users_role_app_roles_fk
        foreign key (role) references public.app_roles(role_key);
    end if;
end;
$$;

commit;
