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
| `pages/10_财务.py` | Cost batches, finance reporting and platform order recalculation | `ui/finance/` | inventory filters, cost-lot repository, batch-first summaries, provider finance adapters |
| `pages/11_物流追踪.py` | ERP shipment acquisition, carrier review, OCR and USPS lookup | `ui/logistics/` | production platform catalog, review models, tracking query/cache, label OCR |
| `pages/12_权限管理.py` | User roles, permissions, production-department assignments and audit | `ui/access/`, `db/access.py` | database-managed role catalog, multi-department employee profiles and audited mutations |
| `pages/13_客户销售出库.py` | Customer, invoice and sales outbound | `ui/inventory/sales/` | linked SKU table, inventory change comparison, atomic sales service |
| `pages/14_仓库调拨.py` | Warehouse request, dispatch and receipt | `ui/inventory/transfers/` | linked SKU options, warehouse batch state, inventory identity rules |
| `pages/17_每日工作.py` | Personal daily checklist, notes and history | `ui/daily_work/` | authenticated operator identity, configurable task templates, date-first history |

## Shared Capability Registry

| Capability | Canonical owner | Reuse rule |
| --- | --- | --- |
| Authentication, permissions and operator identity | `utils/auth/` | Pages consume permission identifiers; never recreate role mappings locally. |
| Personal daily-work records | `db/daily_work.py`, `ui/daily_work/` | Scope templates and dated records to the authenticated username; keep task setup configurable and history grouped by business date. |
| Page width and common layout | `utils/page_layout.py` | Reuse before adding page-specific CSS/layout setup. |
| Inventory apparel size order | `db/inventory/core/constants.py` | Import `SIZE_COLUMNS`; never define another `S` through `5XL` sequence. |
| Human SKU sorting | `utils/sku_sorting.py` | Use for entry, preview, history, costing and detail tables. |
| Inventory scope filters and stale-state reset | `ui/inventory/shared/filters.py` | Extend this filter contract instead of building independent department/category/SKU filters. |
| Inventory filter models | `ui/inventory/shared/filter_models.py` | Reuse pure row filtering, option ordering and title construction outside Streamlit state. |
| Selector value cleanup and business ordering | `utils/option_values.py` | Use `unique_values` and `ordered_values`; pages must not recreate `_values`, `_options`, or `_ordered` helpers with the same semantics. |
| Linked SKU dependency options | `ui/inventory/shared/linked_sku_table.py` | Reuse `material -> brand -> color -> size/model` options in sales, containers and transfers. |
| Cross-ledger before/change/result review | `ui/operations/stock_review.py` | Production inventory and consumable writers use one renderer and the canonical fields `当前库存 / 本次变动 / 调整后库存`; ledger-specific modules only build comparisons and provide identity/unit columns. `ui/inventory/operations/inventory_review.py` remains the production-inventory adapter. |
| Audited batch reversal action | `ui/batches/actions.py` + `db/batches/lifecycle.py` | Production inventory, consumables, sales invoices, and warehouse transfers share confirmation, domain dispatch, feedback, and rerun behavior. Container reversal remains separate because it also transitions container state. |
| Active/reversed batch filtering | `db/batches/filtering.py` | Consumption models, completion status, finance valuation and reversal candidates use one append-only rule: exclude reversal events and the original records they reverse. Audit/history views may retain both explicitly for traceability. |
| Batch selector dependent state | `ui/batches/selectors.py` | Batch-first pages reset selected batches and details whenever the filtered option scope changes. Inventory keeps a compatibility import from its history selector module; consumables use the same contract directly. |
| Container input, display and summaries | `db/inventory/container/input_tables.py`, `tables.py`, `summary_tables.py` | Normalize input once, keep business identity in display conversion, and reuse grouped summaries. |
| Inventory query dimension filters | `db/inventory/core/query_filters.py` | Repository queries compose department/category/brand/material/color/size filters through one owner. |
| Outbound packaging and verification | `db/inventory/operations/outbound.py`, `outbound_specs.py`, `outbound_verification.py` | Pages compose package conversion and persisted-batch verification; do not query package sources locally. |
| Shared inventory planning contracts | `db/planning/stock.py`, `usage.py` | Apparel, UV and consumable adapters first emit one daily-usage evidence contract, then use the same current-stock, coverage, target-stock, reorder, package-conversion and multi-arrival shortage calculations. Source acquisition, matching, model windows and units stay in their domain adapters; do not recreate usage schemas or planning formulas in a page or category module. |
| Shared inventory planning UI | `ui/planning/components.py` | Inventory and consumable pages reuse target-days input and manager summary metrics. Mixed consumable units are never added into a misleading grand total; category pages may add source-specific controls but must not recreate the shared planning controls or summary. |
| Incoming inventory planning | `db/inventory/planning/incoming.py`, `incoming_containers.py`, `incoming_views.py` | Core risk calculations consume a normalized arrival timeline; UI uses the shared forecast/audit views. |
| DTF shirt consumption models and reorder forecast | `db/inventory/planning/consumption_comparison.py`, `ui/inventory/planning/consumption.py`, `automation/production_period.py`, `automation/sync/colored_period.py`, `db/production_consumption.py` | Colored uses the latest 30 complete days of ERP/API production. Black/white keeps warehouse outbound, order baseline and ERP production in one adjustable weighted model. Reorder forecasting shows the 30-day production total, permits total and SKU-level daily-demand overrides, calculates a target-days reorder quantity, and passes that exact adjusted model into in-transit forecasting. Both categories persist into the same production fact table and are separated only by category. |
| Colored daily deduction form | `ui/inventory/planning/colored_daily.py` | Owns preview state, shared three-stage review and apply feedback. `colored_consumption.py` remains the model/view controller and only routes to this focused write workflow. |
| Finance persistence | `db/finance/repository.py`, `consumable_repository.py`, `cost_maintenance.py` | UI consumes stable finance functions; inventory, consumable and maintenance table details stay isolated. |
| Platform finance recalculation | `automation/api/fangguo/finance.py`, `ui/finance/platform_finance.py` | Provider adapters fetch and normalize complete order lines; finance UI owns customer filtering, explicit price-rule preview and export. Never place provider credentials or tenant customer IDs in source code. |
| Platform finance Bill workbook | `ui/finance/bill_workbook.py` | Export one customer-facing XLSX with `Bill汇总` first and `平台订单明细` second; do not split the same bill into separate CSV downloads. |
| Role permission review | `ui/access/permissions.py` | Use role summaries, role-scoped detail and permission-group comparison for daily review; keep the wide full matrix collapsed for advanced audit and CSV export. |
| Cross-ledger inbound business batches | `db/finance/inbound_linking.py`, `ui/finance/inbound_batches.py` | Keep production and consumable ledger IDs independent, but group rows from the same container under one manager-facing inbound batch. |
| SKU group identity changes | `db/inventory/master_data/sku_identity.py` | SKU editors reuse propagation and merge-preview rules before calling the write service. |
| Persistent SKU merge rules | `db/inventory/master_data/sku_merge.py`, `ui/inventory/sku/merge.py` | SKU management owns audited source-to-target rules, size-level previews and current-rule visibility; inventory history is never rewritten. |
| Inventory movement batches and selectors | `ui/inventory/history/core/batches.py`, `core/batch_selector.py` | Reuse batch identity, summary and dependent selector state. |
| Audited batch lifecycle commands | `db/batches/lifecycle.py`, `db/batches/inbound.py` | UI workflows call `reverse_batch` for inventory, daily outbound, consumables, transfers and sales; versioned daily-outbound corrections call `replace_batch`; inventory quantity, posted-container quantity/cost and inbound cost corrections call `replace_inbound_batch`. Domain repositories keep their own atomic transaction rules; historical batches are never updated or deleted as ordinary CRUD. |
| Inventory history filtering and tables | `ui/inventory/history/core/` | Extend shared movement/source/reversal filters, quantity search and tables instead of filtering inside pages. |
| Inventory history workflows | `ui/inventory/history/workflows/` | Compose existing reversal, daily-outbound correction, posted-container quantity/cost correction and SKU-history workflows; do not rebuild stock review. Posted container corrections belong to the selected inventory-ledger batch, while the container page remains read-only after posting. |
| Daily-consumption flow identity | `utils/daily_consumption.py` | Manual and automatic flows share this operational contract and source classification. |
| Automatic daily deduction registry | `automation/sync/daily_inventory_consumption.py` | Register new automatic sources; do not add independent dashboard execution paths. |
| Automatic deduction source preview | `automation/sync/daily_flow_preview.py` | Dashboard flows reuse the same single-source preparation, preview and audit fields. |
| Daily outbound entry and review | `ui/inventory/operations/outbound_entry.py`, `outbound_import.py`, `outbound_review.py` | Compose entry/import with the shared inventory review; do not duplicate conversion or shortage handling in pages. |
| Versioned daily outbound persistence | `db/inventory/operations/daily_outbound_versions.py` | Create, edit and void logical daily-outbound batches through one audited owner; voiding restores inventory and updates the business batch status together. |
| Inventory batch quantity calibration | `db/inventory/operations/batch_corrections.py`, `ui/inventory/history/workflows/batch_correction.py` | From the shared inventory-ledger batch selector, correct carton-rule, transcription or total errors by entering the corrected absolute batch quantity; preserve the source batch and post only the audited signed delta with the standard current/change/result review. |
| System deduction review adapter | `ui/inventory/operations/system_deduction.py` + `ui/operations/stock_review.py` | UV, colored and dashboard previews first normalize to the canonical `当前库存 / 本次变动 / 调整后库存` contract, then use the same three-stage renderer as manual inventory writes. Source, mapping status and unresolved quantities remain visible as audit columns. |
| Container UI tables | `ui/inventory/container/tables.py`, `detail_tables.py`, `summary_tables.py` | Use the table facade; detail, packaging and grouped summaries retain separate owners. |
| In-transit container workflow | `ui/inventory/container/transit_view.py`, `db/inventory/container/repository.py` | Container pages compose the shared list/summary/detail operation instead of rebuilding state and progress tables. Existing editable business containers append formal SKU rows through `append_inventory_container_items`, preserving one batch identity and an audit event. |
| Consumable SKU administration | `ui/consumables/sku_models.py`, `sku_create.py`, `sku_catalog.py` | Reuse model transformations for copy defaults and catalog diffs; UI tabs do not reimplement them. |
| Consumable stocktake package validation | `ui/consumables/operations/validation.py` | Stock initialization requires package sizes; ordinary inbound/issue accepts package or base-unit entry and must not reuse this stricter rule. |
| Consumable quantity conversion | `ui/consumables/units.py` | All inbound, issue, stocktake, stock and history views use box conversion when configured and otherwise preserve the SKU base unit. |
| Consumable daily completion status | `ui/consumables/completion.py`, `db/inventory/dashboard_completion.py`, `db/consumables/repository.py` | The consumable page and inventory summary derive completion from the same active, non-reversed issue batches. A reviewed day already covered elsewhere may use an audited `completion_ack` batch with no stock change; never move an arbitrary issue batch merely to clear a reminder. |
| Container inventory posting action | `ui/inventory/container/posting.py` | Pending, same-day and “到柜并直接入库” actions call `post_container_with_feedback`; do not repeat RPC, operator, success and rerun handling. Arrival confirmation remains a separate container-state action. |
| Sales parties and invoice signing | `ui/inventory/sales/customer_section.py`, `invoice_review.py` | Sales pages compose customer selection and preview-before-signing; inventory validation remains shared. |
| Production platform catalog | `automation/production.py` | Logistics and production pages reuse the same department/platform ownership. |
| ERP product normalization | `utils/erp/` | Source adapters feed shared normalized records; do not normalize the same platform in UI code. |
| Humbird production and logistics APIs | `humbird_erp/`, `automation/api/humbird/` | The publishable package owns API-key transport, pagination, product hydration and waybill lookup. The provider package owns credentials, rate-limit backoff, request-header token capture, production and shipment adapters. Haloo and Longfeng use the three-level fallback; Putian starts from the encrypted database-token route because it has no official Open API. Compatibility modules contain no logic. |
| SDS production and logistics API | `automation/api/sds/` | Authentication, production reads and parcel/label reads share the SDS provider package; workflows import its public facade. |
| S2B production and logistics API | `automation/api/s2b/` | Production records, production parsing, 1,000-row paged order/tracking reads and label calls share the S2B provider package; browser login remains a replaceable authentication fallback. |
| 19DIY production and logistics API | `automation/api/diy19/` | 七创 and 一朵云 share provider authentication, production reads, shipment reads and provider response normalization. |
| Provider-neutral integration contracts | `automation/integrations/` | ERP providers reuse carrier classification and workflow-stage semantics without importing page or logistics-controller packages. |
| Daily usage model | `utils/daily_usage_model.py` | Inventory and consumable planning reuse common daily-rate calculations where units and semantics match. |
| Google Sheets returned-range matching | `utils/google_sheets.py` | All Sheets batch readers use the shared normalized range lookup. |
| Logistics carrier/label review | `automation/integrations/carriers.py`, `ui/logistics/review/` | Compose shared carrier classification with the review model, OCR runner, state and view; only ordinary USPS relationships backed by an official USPS check are persisted. Keep `page.py` as controller only. |
| ERP logistics business stages | `automation/logistics/stages.py` | All connectors map their own codes to 未接单、已接单（生产中）、已发货; 已发货 means production and QA completed, not merely label creation. UI pages reuse these labels and codes. |
| SDS logistics date and label acquisition | `automation/api/sds/shipments.py` | Convert New York business-day boundaries to Asia/Shanghai, read the selected SDS stage, then fetch order label details concurrently with platform-specific progress. |
| ERP logistics platform concurrency | `ui/logistics/sync_view.py` | Users choose one to eight ERP platform workers, default four. The setting excludes OCR; live status remains one stable row per platform and completed reads are persisted in completion order. |
| USPS tracking input/query/results | `ui/logistics/tracking/` | Reuse input normalization, cache/query, label and origin components. |
| Logistics daily platform summary | `db/logistics/summary.py`, `ui/logistics/summary_model.py`, `summary_detail.py`, `summary_view.py` | Persist ERP relationships first, associate USPS checks through `logistics_tracking_check_sources`, then present date/platform batches before order-level PDF and OCR detail. |
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
