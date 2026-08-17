begin;

update public.app_permissions
set permission_name = 'USPS官方API查询',
    description = '查询数据库缓存或调用USPS官方Tracking API'
where permission_key = 'can_view_logistics';

update public.app_permissions
set permission_name = '生产物流：ERP同步、OCR与管理',
    description = '生产人员执行ERP同步、面单OCR、批量下载、物流总结与审核管理'
where permission_key = 'can_manage_logistics';

update public.app_permissions
set permission_name = '库存出入库',
    description = '创建、修改、撤销库存入库和出库批次'
where permission_key = 'can_edit_inventory';

insert into public.app_role_permissions (role_key, permission_key)
values
    ('producer', 'can_manage_logistics'),
    ('after_sales', 'can_view_logistics'),
    ('after_sales', 'can_manage_logistics'),
    ('after_sales', 'can_edit_inventory')
on conflict do nothing;

delete from public.app_role_permissions
where (
    permission_key = 'can_view_logistics'
    and role_key not in ('after_sales', 'admin')
) or (
    permission_key = 'can_manage_logistics'
    and role_key not in ('producer', 'after_sales', 'admin')
) or (
    permission_key = 'can_edit_inventory'
    and role_key not in ('after_sales', 'admin')
);

insert into public.app_role_permissions (role_key, permission_key)
select 'after_sales', permission_key
from public.app_permissions
where permission_key not in (
    'can_view_cost', 'can_manage_cost',
    'can_view_finance_reports', 'can_view_finance_dashboard',
    'can_manage_access'
)
on conflict do nothing;

delete from public.app_role_permissions
where role_key = 'after_sales'
  and permission_key in (
      'can_view_cost', 'can_manage_cost',
      'can_view_finance_reports', 'can_view_finance_dashboard',
      'can_manage_access'
  );

commit;
