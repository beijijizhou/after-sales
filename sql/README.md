# SQL 目录说明

SQL 按业务领域和用途存放。新增脚本应进入对应目录，不再放在 `sql/`
根目录。编号文件按编号执行；没有编号的迁移必须先阅读文件头的前置条件。

| 目录 | 用途 | 文件数 |
| --- | --- | ---: |
| `access/` | 权限、角色、初始账号和人员/角色变更审计 | 14 个迁移 SQL |
| `after_sales/` | 售后字段、条码修复和烫印膜核对账本 | 3 |
| `production/` | 生产条码历史和多件订单刷新 | 2 |
| `production/summaries/` | 人员平台、小时、配对工作流和区间汇总 | 5 |
| `production/consumption/` | ERP/API 每日平台消耗及同步审计 | 2 |
| `inventory/schema/` | 库存基础表和主数据结构 | 5 |
| `inventory/operations/` | 调整、盘点设置、每日出库版本、批次、快照、撤销、SKU 更新和并入规则 | 8 |
| `inventory/containers/` | 货柜表、到柜和历史 | 3 |
| `inventory/warehouses/` | 25/60/70 仓库分布、库位参考和调拨单 | 4 |
| `inventory/planning/` | 消耗与预测模型 | 1 |
| `inventory/costs/` | 成本批次、待分配批次、调整、撤销和报表 | 7 个 SQL |
| `inventory/imports/` | 可重复检查的数据导入脚本 | 4 |
| `inventory/data_fixes/` | 有明确目标的一次性数据修复 | 2 |
| `consumables/` | 耗材表、流水、撤销和验证 | 4 |
| `logistics/` | 物流审查、USPS用量、查询来源与OCR审计 | 3 |
| `personal_work/` | 个人每日任务模板、按日记录和页面权限 | 1 |

## 维护规则

- 表结构、业务函数、数据导入和一次性修复不能混在同一文件。
- 超过约 200 行且包含多个独立函数的脚本，应按依赖顺序拆成编号文件。
- 数据导入和修复脚本必须写明日期、适用数据、前置条件和核验方式。
- 生产环境执行前先做预检，执行后核对受影响行数和业务总数。
- 文件移动后必须同步更新应用中的 SQL Editor 提示路径。

## 生产汇总安装顺序

生产汇总函数按职责拆分，按编号执行：

1. `production/summaries/01_person_platform.sql`
2. `production/summaries/02_hourly_totals.sql`
3. `production/summaries/03_hourly_people.sql`
4. `production/summaries/04_pair_workflow.sql`
5. `production/summaries/05_qa_period.sql`

每日平台消耗按 `production/consumption/README.md` 执行 `01–02`。

## 动态角色权限安装顺序

角色权限迁移按职责存放在 `access/role_management/`，从
`01_schema.sql` 到 `14_employee_profile_management.sql` 按编号执行。具体职责和
安装后核验项目见该目录的 `README.md`。
