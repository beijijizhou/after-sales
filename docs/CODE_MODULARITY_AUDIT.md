# Code Modularity Audit

本审查基于当前活跃目录中的 Python 和 SQL 文件，排除了 `.venv/`、缓存、
临时审计脚本和导出产物。目标不是机械地让所有文件一样长，而是让页面只做
编排、业务规则有明确归属、相似模块集中，并将目录稳定在约 4–5 个核心文件。

## 已完成

- `sql/` 根目录的混合脚本已按权限、售后、生产和库存子领域归档。
- 库存 SQL 又按结构、操作、货柜、计划、成本、导入和数据修复区分。
- 应用内所有已发现的 SQL Editor 提示已改为新路径。
- `sql/README.md` 记录目录职责和后续拆分规则。
- 库存多语言静态词典已迁入 `ui/inventory/i18n_catalog.py`，
  `ui/inventory/i18n.py` 只保留 Streamlit 状态与渲染适配，并维持原公开接口。
- Google Sheets 范围匹配与 S2B 可见按钮点击已分别收敛为共享集成助手，
  删除同步和浏览器调用链中的逐字重复实现。
- 物流页面控制器已从千行级缩减为约 55 行，只保留页面入口与标签编排。
  ERP同步放在 `sync_view.py` 和 `source_gateway.py`；物流审核拆到
  `ui/logistics/review/` 的模型、视图、OCR执行、格式化和状态组件。
- 原 600 余行 USPS 查询控制器已拆到 `ui/logistics/tracking/`，分别负责
  输入规范化、查询与缓存、面单信息、始发地展示和页面编排。
- 原 583 行库存历史控制器已拆为 `history/core/` 的批次、筛选、表格和
  数量搜索组件，以及 `history/workflows/` 的撤销、修正和 SKU 历史流程；
  库存变动核对继续复用统一的 `adjustment_preview` 契约。
- 库存写入的三段式核对已集中到 `inventory_review.py`，盘点比较与宽表编辑
  分离；销售、出库、货柜入库、修正和撤销继续组合同一契约。
- 货柜表已拆为输入规范化、展示转换和汇总表；出库已拆出包装规格来源与
  持久化校验，避免页面重复查询和签名比较。
- 到货预测已拆为核心计算、货柜时间线和管理/核对视图；UV 与彩色消耗页面
  分别收敛到专属视图，彩色生产同步也分离来源读取和模型计算。
- 财务仓储层已拆为库存流水、耗材估值和成本维护；SKU 身份传播与合并预览
  已集中到主数据身份模块。

## 高优先级拆分队列

| 文件 | 当前行数 | 建议边界 |
| --- | ---: | --- |
| `ui/inventory/dashboard.py` | 496 | 总览、完成状态、自动补扣编排 |
| `ui/inventory/operations/outbound.py` | 451 | 页面状态、包装输入、提交确认 |
| `automation/sync/daily_inventory_consumption.py` | 351 | 批量编排、来源准备、单流程预览 |
| `ui/inventory/container/tables.py` | 269 | 列定义、概览表、明细表、格式化 |
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
- 物流模块后续新增逻辑必须进入现有 `review/` 或 `tracking/` 职责文件，
  `page.py` 不再承载同步、OCR、查询或表格转换实现。

## 审查结论

当前项目的主要问题不是缺少目录，而是新旧入口并存，以及少数控制器继续承载
查询、业务计算和渲染三种职责。后续应按上面的队列逐个调用链拆分；每完成一个
领域就删除已无调用的兼容层并更新 `CURRENT_STATE.md`，不建议一次性批量改动所有
库存写入路径。
