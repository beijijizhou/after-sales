# 动态角色权限安装

在 Supabase SQL Editor 中按顺序执行以下脚本：

1. `01_schema.sql`：角色、权限和审计表结构。
2. `02_catalog_and_roles.sql`：权限目录、初始角色和初始权限组合。
3. `03_access_guard.sql`：权限管理员身份校验函数。
4. `04_user_access_rpc.sql`：用户角色与启用状态变更函数。
5. `05_role_definition_rpc.sql`：角色创建、权限组合和角色审计函数。
6. `06_login_and_grants.sql`：登录权限读取、数据库授权和接口刷新。
7. `07_logistics_production_ownership.sql`：售后拥有除财务、成本和系统权限管理外的全部业务权限；管理员拥有全部权限；生产人员和主管不能调用 USPS API。
8. `08_employee_departments.sql`：把旧 `department` 迁移为岗位兼容字段，建立 DTF/UV/3D 多部门关联；现有员工默认 DTF。
9. `09_employee_department_admin.sql`：后台多部门与角色联合修改接口及审计。
10. `10_employee_department_queries.sql`：登录和 `qa-barcode-listener` 使用的兼容查询接口。
11. `11_employee_auth_compatibility.sql`：注册账号和质检扫码项目共用的数据库端安全登录接口。
12. `12_people_management.sql`：人员名单、离职/复职权限、状态变更接口和审计记录。
13. `13_supervisor_people_management.sql`：把人员名单及离职/复职权限授予主管角色，并修正用户角色变更审计的原角色记录。
14. `14_employee_profile_management.sql`：允许主管审计式调整员工岗位和生产部门。

这些脚本可重复执行。第二步只在角色尚无权限记录时写入初始组合，
不会覆盖管理员已经在页面中保存的角色权限。

`01_schema.sql` 会识别 2026 年 7 月旧版的宽权限表（使用 `role` 主键和
多个布尔权限列），将它保留为 `app_role_permissions_legacy_wide`，再创建
新版 `(role_key, permission_key)` 关系表。这个兼容迁移不会删除旧数据；
确认新版权限页面正常后，旧备份仍需由管理员自行决定是否归档或删除。

安装后使用管理员账号登录，在“权限管理”页面核对：

- “角色配置”能读取现有角色和权限目录；
- “权限矩阵”展示数据库中的实时组合；
- “变更记录”分别展示用户角色与角色配置审计记录。

再进入“人员管理”核对：员工名单包含无登录账号的员工；主管和管理员可以预览并
确认岗位、生产部门及离职/复职变化；完成后“人员变更记录”保留前后值和操作人。
