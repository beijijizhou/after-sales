# Cross-Page Function Catalog

Use this catalog before implementing a feature. Search by business capability,
fields, user labels, database tables/RPCs, and tests before searching by a new
function name. The catalog records ownership and composition points; it is not
an activity log.

## Page Capabilities

| Entry page | Business capability | Primary UI owner | Existing composition points |
| --- | --- | --- | --- |
| `app.py` | Home and problem tracking | application entry and shared UI | authentication, page layout, Supabase client |
| `pages/0_注册.py` | User registration | page controller | shared authentication and Supabase client |
| `pages/1_质检.py` | QA scanning and production summary | `ui/production/summary.py` | shared production filters, time utilities, authentication |
| `pages/2_烫印.py` | Hotstamp scanning and production summary | `ui/production/summary.py` | same production summary contract as QA with a different operation field |
| `pages/3_平台.py` | Platform production detail | `ui/platform_summary.py` | production database summaries and shared time handling |
| `pages/4_库存.py` | Production inventory operations | `ui/inventory/summary.py` | shared inventory filters, SKU order, stock review, batch history, forecasting |
| `pages/4_SKU管理.py` | Production SKU administration | `ui/inventory/sku/` | shared master data, SKU sorting, active-state rules, linked SKU options |
| `pages/4_库存总结.py` | Daily inventory completion workbench | `ui/inventory/dashboard.py` | daily-consumption registry, automatic preview/apply contract, batch status |
| `pages/5_货柜安排.py` | Container planning, arrival, posting, reversal | `ui/inventory/container/` | linked SKU options, inventory change comparison, batch history, forecasts |
| `pages/6_售后查询.py` | After-sales and barcode-operation search | `ui/after_sales_ui.py`, `ui/barcode_operations_ui.py` | shared authentication, search/database adapters |
| `pages/7_生产数据.py` | Production synchronization and review | `ui/production_data/` | platform catalog, ERP normalization, synchronized cache |
| `pages/8_图片拉伸.py` | Phone-case image and dieline processing | `ui/image_tools/` | shared phone-case catalog and image utilities |
| `pages/9_耗材库存.py` | Consumable stock, issue, inbound, ledger, SKU and planning | `ui/consumables/` | batch review concepts; separate consumable persistence and unit conversion |
| `pages/10_财务.py` | Cost batches and finance reporting | `ui/finance/` | inventory filters, cost-lot repository, batch-first summaries |
| `pages/11_物流追踪.py` | ERP shipment acquisition, carrier review, OCR and USPS lookup | `ui/logistics/` | production platform catalog, review models, tracking query/cache, label OCR |
| `pages/12_权限管理.py` | User roles, permissions and audit | `ui/access/` | database-managed role catalog and audited mutations |
| `pages/13_客户销售出库.py` | Customer, invoice and sales outbound | `ui/inventory/sales/` | linked SKU table, inventory change comparison, atomic sales service |
| `pages/14_仓库调拨.py` | Warehouse request, dispatch and receipt | `ui/inventory/transfers/` | linked SKU options, warehouse batch state, inventory identity rules |

## Shared Capability Registry

| Capability | Canonical owner | Reuse rule |
| --- | --- | --- |
| Authentication, permissions and operator identity | `utils/auth/` | Pages consume permission identifiers; never recreate role mappings locally. |
| Page width and common layout | `utils/page_layout.py` | Reuse before adding page-specific CSS/layout setup. |
| Inventory apparel size order | `db/inventory/core/constants.py` | Import `SIZE_COLUMNS`; never define another `S` through `5XL` sequence. |
| Human SKU sorting | `utils/sku_sorting.py` | Use for entry, preview, history, costing and detail tables. |
| Inventory scope filters and stale-state reset | `ui/inventory/shared/filters.py` | Extend this filter contract instead of building independent department/category/SKU filters. |
| Inventory filter models | `ui/inventory/shared/filter_models.py` | Reuse pure row filtering, option ordering and title construction outside Streamlit state. |
| Selector value cleanup and business ordering | `utils/option_values.py` | Use `unique_values` and `ordered_values`; pages must not recreate `_values`, `_options`, or `_ordered` helpers with the same semantics. |
| Linked SKU dependency options | `ui/inventory/shared/linked_sku_table.py` | Reuse `material -> brand -> color -> size/model` options in sales, containers and transfers. |
| Inventory before/change/result review | `ui/inventory/operations/inventory_review.py` | Every inventory-writing UI composes this review; adjustment-specific comparison and editing remain separate. |
| Container input, display and summaries | `db/inventory/container/input_tables.py`, `tables.py`, `summary_tables.py` | Normalize input once, keep business identity in display conversion, and reuse grouped summaries. |
| Inventory query dimension filters | `db/inventory/core/query_filters.py` | Repository queries compose department/category/brand/material/color/size filters through one owner. |
| Outbound packaging and verification | `db/inventory/operations/outbound.py`, `outbound_specs.py`, `outbound_verification.py` | Pages compose package conversion and persisted-batch verification; do not query package sources locally. |
| Incoming inventory planning | `db/inventory/planning/incoming.py`, `incoming_containers.py`, `incoming_views.py` | Core risk calculations consume a normalized arrival timeline; UI uses the shared forecast/audit views. |
| Colored production consumption | `automation/sync/colored_source.py`, `colored_models.py`, `dtf_colored_inventory.py` | Source cache, daily model and inventory deduction remain separate and composable. |
| Finance persistence | `db/finance/repository.py`, `consumable_repository.py`, `cost_maintenance.py` | UI consumes stable finance functions; inventory, consumable and maintenance table details stay isolated. |
| Cross-ledger inbound business batches | `db/finance/inbound_linking.py`, `ui/finance/inbound_batches.py` | Keep production and consumable ledger IDs independent, but group rows from the same container under one manager-facing inbound batch. |
| SKU group identity changes | `db/inventory/master_data/sku_identity.py` | SKU editors reuse propagation and merge-preview rules before calling the write service. |
| Persistent SKU merge rules | `db/inventory/master_data/sku_merge.py`, `ui/inventory/sku/merge.py` | SKU management owns audited source-to-target rules, size-level previews and current-rule visibility; inventory history is never rewritten. |
| Inventory movement batches and selectors | `ui/inventory/history/core/batches.py`, `core/batch_selector.py` | Reuse batch identity, summary and dependent selector state. |
| Inventory history filtering and tables | `ui/inventory/history/core/` | Extend shared movement/source/reversal filters, quantity search and tables instead of filtering inside pages. |
| Inventory history workflows | `ui/inventory/history/workflows/` | Compose existing reversal, daily-outbound correction, posted-container quantity/cost correction and SKU-history workflows; do not rebuild stock review. Posted container corrections belong to the selected inventory-ledger batch, while the container page remains read-only after posting. |
| Daily-consumption flow identity | `utils/daily_consumption.py` | Manual and automatic flows share this operational contract and source classification. |
| Automatic daily deduction registry | `automation/sync/daily_inventory_consumption.py` | Register new automatic sources; do not add independent dashboard execution paths. |
| Automatic deduction source preview | `automation/sync/daily_flow_preview.py` | Dashboard flows reuse the same single-source preparation, preview and audit fields. |
| Daily outbound entry and review | `ui/inventory/operations/outbound_entry.py`, `outbound_import.py`, `outbound_review.py` | Compose entry/import with the shared inventory review; do not duplicate conversion or shortage handling in pages. |
| System deduction display model | `ui/inventory/operations/system_deduction.py` | UV, colored and dashboard previews reuse signed outbound/result column normalization. |
| Container UI tables | `ui/inventory/container/tables.py`, `detail_tables.py`, `summary_tables.py` | Use the table facade; detail, packaging and grouped summaries retain separate owners. |
| In-transit container workflow | `ui/inventory/container/transit_view.py` | Container pages compose the shared list/summary/detail operation instead of rebuilding state and progress tables. |
| Consumable SKU administration | `ui/consumables/sku_models.py`, `sku_create.py`, `sku_catalog.py` | Reuse model transformations for copy defaults and catalog diffs; UI tabs do not reimplement them. |
| Consumable quantity conversion | `ui/consumables/units.py` | All inbound, issue, stocktake, stock and history views use box conversion when configured and otherwise preserve the SKU base unit. |
| Container inventory posting action | `ui/inventory/container/posting.py` | Pending and same-day posting call `post_container_with_feedback`; do not repeat RPC, operator, success and rerun handling. |
| Sales parties and invoice signing | `ui/inventory/sales/customer_section.py`, `invoice_review.py` | Sales pages compose customer selection and preview-before-signing; inventory validation remains shared. |
| Production platform catalog | `automation/production.py` | Logistics and production pages reuse the same department/platform ownership. |
| ERP product normalization | `utils/erp/` | Source adapters feed shared normalized records; do not normalize the same platform in UI code. |
| Humbird official production and logistics API | `automation/api/humbird/open_client.py`, `automation/logistics/humbird.py` | Haloo production and waybill acquisition share the official Open Platform client; keep API-key auth, product/SKU hydration and order-level waybill lookup out of UI code. |
| Daily usage model | `utils/daily_usage_model.py` | Inventory and consumable planning reuse common daily-rate calculations where units and semantics match. |
| Google Sheets returned-range matching | `utils/google_sheets.py` | All Sheets batch readers use the shared normalized range lookup. |
| Logistics carrier/label review | `ui/logistics/review/` | Compose model, OCR runner, state and view; keep `page.py` as controller only. |
| USPS tracking input/query/results | `ui/logistics/tracking/` | Reuse input normalization, cache/query, label and origin components. |
| S2B visible page actions | `automation/playwright/s2b/page_actions.py` | Browser workflows reuse shared visible exact-text interaction. |
| Barcode search candidates and previews | `utils/barcode_patterns.py` | Exact and fuzzy search strategies reuse canonical candidate-to-input and preview schemas; UI only composes them. |

## Reuse Review Gate

Before adding code:

1. Identify the capability and its business inputs, outputs, side effects and
   audit requirements.
2. Check the page row and shared registry above.
3. Search sibling pages and shared modules using business field names, Chinese
   labels, table/RPC names and relevant tests.
4. Prefer composition, then interface extension, then shared-core extraction.
5. Add a new implementation only when business semantics differ, and record
   its ownership here.
6. For an extracted shared core, migrate every active duplicate and add a
   contract test at the shared boundary.

Similar appearance is not sufficient for reuse. Production inventory and
consumables, for example, share review and audit concepts but retain separate
persistence and unit-conversion rules.
