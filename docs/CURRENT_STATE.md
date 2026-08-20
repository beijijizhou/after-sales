# Current System Map

This file describes where active behavior lives. Update it after structural
refactors, not after every small feature.

## Entry Points

- Home/problem tracking: `app.py`
- People management and employee registration: `pages/0_注册.py`, with UI
  ownership in `ui/people/`
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
- Admin access management: `pages/12_权限管理.py`
- Personal daily work: `pages/17_每日工作.py`

## Major Modules

- Authentication and navigation: `utils/auth/`
- User-role administration: `db/access.py` and `ui/access/`
- Employee roster, registration, departure/reactivation and status audit:
  `db/access.py`, `ui/people/`, and
  `sql/access/role_management/12_people_management.sql`
- Personal daily-work templates, dated records, and history:
  `db/daily_work.py` and `ui/daily_work/`
- Inventory persistence and rules: `db/inventory/`
- Inventory UI: `ui/inventory/`
- Inventory history data components: `ui/inventory/history/core/`; history
  page, reversal, correction, and SKU workflows:
  `ui/inventory/history/workflows/`.
- Container workflow: `db/inventory/container/` and
  `ui/inventory/container/`
- Consumables: `db/consumables/` and `ui/consumables/`, including
  consumable reorder forecasting in `db/consumables/planning.py` and
  `ui/consumables/planning.py`
- Logistics label review: `automation/logistics/`, `db/logistics/`, and
  `ui/logistics/`; page orchestration lives in `ui/logistics/page.py`, ERP
  source selection in `sync_view.py` and `source_gateway.py`, carrier and
  label review in `ui/logistics/review/`, and USPS lookup in
  `ui/logistics/tracking/`. Daily platform summaries and order-level drill-down
  live in `ui/logistics/summary_*.py`, backed by `db/logistics/summary.py` and
  the persisted USPS-to-shipment source association.
- Finance: `db/finance/` and `ui/finance/`; provider order-fee acquisition
  lives in provider adapters such as `automation/api/fangguo/finance.py`.
- Finance persistence is separated into inventory reporting
  (`db/finance/repository.py`), consumable valuation
  (`consumable_repository.py`), and missing-cost maintenance
  (`cost_maintenance.py`).
- Production summaries: `utils/production/` and `ui/production/`
- ERP normalization: `utils/erp/`
- Publishable Humbird Open Platform client: `humbird_erp/`; project credential,
  legacy-token fallback, normalization, and persistence adapters remain under
  `automation/api/humbird/`.
- Shared Google Sheets response normalization: `utils/google_sheets.py`
- Shared S2B browser interactions: `automation/playwright/s2b/page_actions.py`
- Inventory localization runtime and static catalog:
  `ui/inventory/i18n.py` and `ui/inventory/i18n_catalog.py`
- Shared daily-consumption flow definitions and source classification:
  `utils/daily_consumption.py`
- Shared daily-usage aggregation and forecast-model primitives:
  `utils/daily_usage_model.py`
- Inventory workbench and automatic-deduction registry:
  `ui/inventory/dashboard*.py`, `db/inventory/dashboard*.py`,
  `automation/sync/daily_inventory_consumption.py`, and the reusable
  single-source preview in `automation/sync/daily_flow_preview.py`.
- Daily outbound is composed from the controller and its entry, import and
  review components in `ui/inventory/operations/outbound*.py`.
- Container list, detail/packaging, and grouped summaries are separated in
  `ui/inventory/container/tables.py`, `detail_tables.py`, and
  `summary_tables.py`; in-transit progress and operations live in
  `transit_view.py`.
- Consumable SKU creation/catalog share `ui/consumables/sku_models.py`;
  customer sales separates party editing and preview-before-signing under
  `ui/inventory/sales/`.
- Shared stock-write review: `ui/inventory/operations/inventory_review.py`;
  adjustment comparison and editing remain in `adjustment_preview.py` and
  `adjustment_editor.py`.
- Incoming planning is split between core calculation, container arrival
  aggregation, and human-facing views in `db/inventory/planning/incoming*.py`.
- Colored production consumption separates cached sources, usage models, and
  inventory deduction under `automation/sync/colored_*.py` and
  `dtf_colored_inventory.py`.
- Production collection: `automation/api/`, `automation/playwright/`, and
  `automation/sync/`
- ERP provider ownership: `automation/api/<provider>/` contains each
  provider's authentication, production API, logistics API, payloads and
  provider-specific response handling. `automation/logistics/` owns shared
  workflow composition, OCR, USPS and compatibility concerns only; provider-
  neutral carrier and stage contracts live in `automation/integrations/`.
- Phone-case image and dieline logic: `utils/image_tools/`,
  `ui/image_tools/`, and `assets/dielines/`
- Database scripts: `sql/`, grouped by business domain; inventory scripts are
  further grouped under `sql/inventory/` by schema, operations, containers,
  planning, costs, imports, and one-time data fixes.
- Production summary functions: `sql/production/summaries/`, split by person
  platform, hourly totals, hourly people, pair workflow, and period summary.

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
- Page requirements use stable permission identifiers in code; role creation,
  role labels, and role-permission composition are managed in the database and
  audited through the admin access-management page.
