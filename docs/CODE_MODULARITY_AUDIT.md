# Code Modularity Audit

本审查基于当前活跃目录中的 Python 和 SQL 文件，排除了 `.venv/`、缓存、
临时审计脚本和导出产物。目标不是机械地让所有文件一样长，而是让页面只做
编排、业务规则有明确归属、相似模块集中，并将目录稳定在约 4–5 个核心文件。

## 已完成

- `sql/` 根目录的混合脚本已按权限、售后、生产和库存子领域归档。
- 库存 SQL 又按结构、操作、货柜、计划、成本、导入和数据修复区分。
- 应用内所有已发现的 SQL Editor 提示已改为新路径。
- `sql/README.md` 记录目录职责和后续拆分规则。

## 高优先级拆分队列

| 文件 | 当前行数 | 建议边界 |
| --- | ---: | --- |
| `ui/inventory/i18n.py` | 588 | `i18n/en.py`、`i18n/es.py`、`i18n/runtime.py`，由包入口保持现有接口 |
| `ui/inventory/planning/comparison.py` | 476 | 查询状态、指标表、趋势视图、页面编排 |
| `db/inventory/planning/incoming.py` | 390 | 到货匹配、风险计算、展示模型、公共格式化 |
| `db/inventory/container/tables.py` | 338 | 查询、规范化、写入、兼容字段映射 |
| `ui/inventory/container/tables.py` | 269 | 列定义、概览表、明细表、格式化 |
| `ui/inventory/history/history.py` | 241 | 筛选编排、SKU 时间线、撤销入口 |
| `ui/inventory/stock/cost_summary.py` | 238 | 成本权限、汇总计算、表格渲染 |
| `ui/consumables/operations/stock_tables.py` | 237 | 库存概览、流水表、低库存提示 |

这些文件位于库存、成本或货柜关键调用链。拆分时必须保持公开函数签名，并运行
对应的库存/货柜/成本测试，不能只用行数作为拆分依据。

## 中优先级整理

- `ui/inventory/` 仍保留若干顶层兼容入口，同时已有 `stock/`、`history/`、
  `planning/` 和 `operations/` 子包。确认没有外部调用后，应逐步删除只做转发的
  旧入口，避免新代码继续引用两套路径。
- `db/inventory/` 同时存在顶层模块和 `core/`、`operations/`、`planning/`、
  `master_data/` 子包。顶层文件若仅用于兼容，应标注弃用入口；仍含业务逻辑的
  文件应迁入对应子包。
- `automation/sync/` 混合了日常同步、一次性初始化和历史修复。建议后续分为
  `runtime/`、`imports/`、`maintenance/`，每个目录保留约 4–5 个相关入口。
- `utils/erp/` 按 ERP 平台横向增长。建议每个平台形成包含配置、解析、目录映射
  和规范化的子包，公共协议留在包根部。
- `ui/logistics/page.py` 是当前未提交的新模块，不在本轮移动。稳定后可拆为筛选、
  同步操作、审查详情和结果表四个视图文件。

## 审查结论

当前项目的主要问题不是缺少目录，而是新旧入口并存，以及少数控制器继续承载
查询、业务计算和渲染三种职责。后续应按上面的队列逐个调用链拆分；每完成一个
领域就删除已无调用的兼容层并更新 `CURRENT_STATE.md`，不建议一次性批量改动所有
库存写入路径。

