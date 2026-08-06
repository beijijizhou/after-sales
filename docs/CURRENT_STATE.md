# Current System Map

This file describes where active behavior lives. Update it after structural
refactors, not after every small feature.

## Entry Points

- Home/problem tracking: `app.py`
- Registration: `pages/0_注册.py`
- QA: `pages/1_质检.py`
- Hotstamp: `pages/2_烫印.py`
- Platform detail: `pages/3_平台.py`
- Production inventory: `pages/4_库存.py`
- Inventory workbench: `pages/4_库存总结.py`
- Containers: `pages/5_货柜安排.py`
- After-sales search: `pages/6_售后查询.py`
- Production data collection: `pages/7_生产数据.py`
- Phone-case image processing: `pages/8_图片拉伸.py`
- Consumables: `pages/9_耗材库存.py`
- Finance: `pages/10_财务.py`
- Logistics label review: `pages/11_物流追踪.py`

## Major Modules

- Authentication and navigation: `utils/auth/`
- Inventory persistence and rules: `db/inventory/`
- Inventory UI: `ui/inventory/`
- Container workflow: `db/inventory/container/` and
  `ui/inventory/container/`
- Consumables: `db/consumables/` and `ui/consumables/`
- Logistics label review: `automation/logistics/`, `db/logistics/`, and
  `ui/logistics/`
- Finance: `db/finance/` and `ui/finance/`
- Production summaries: `utils/production/` and `ui/production/`
- ERP normalization: `utils/erp/`
- Shared daily-consumption flow definitions and source classification:
  `utils/daily_consumption.py`
- Inventory workbench and automatic-deduction registry:
  `ui/inventory/dashboard.py` and
  `automation/sync/daily_inventory_consumption.py`
- Production collection: `automation/api/`, `automation/playwright/`, and
  `automation/sync/`
- Phone-case image and dieline logic: `utils/image_tools/`,
  `ui/image_tools/`, and `assets/dielines/`
- Database scripts: `sql/`, grouped by business domain; inventory scripts are
  further grouped under `sql/inventory/` by schema, operations, containers,
  planning, costs, imports, and one-time data fixes.

## Inventory Model

- Master data: departments, categories, brands, and SKUs.
- Current quantity: `inventory_items`.
- Auditable ledger: `inventory_movements`.
- Batch imports and snapshots support historical views.
- SKU initialization UI:
  `ui/inventory/sku/initialization.py`.
- SKU initialization logic:
  `db/inventory/master_data/initialization.py`.
- Container state is represented by persisted business facts; transition
  rules stay in application code where possible.

## Active Conventions

- Top-level inventory filters drive all inventory tabs.
- SKU management reuses the selected top-level department.
- Inventory SKU identity is department/category/brand/material/color/size or
  model.
- UV currently contains iron-board art, wood product, thermos, and phone-case
  categories.
- Stable access behavior comes from code-defined role permissions.
