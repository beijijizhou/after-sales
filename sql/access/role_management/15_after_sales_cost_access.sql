begin;

insert into public.app_role_permissions (role_key, permission_key)
values
    ('after_sales', 'can_view_cost'),
    ('after_sales', 'can_manage_cost')
on conflict do nothing;

delete from public.app_role_permissions
where role_key = 'after_sales'
  and permission_key in (
      'can_view_finance_reports',
      'can_view_finance_dashboard'
  );

commit;
