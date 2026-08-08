# Business Rules

## Organization

- Departments are extensible. Current departments include `DTF`, `UV`, and
  `3D`; do not encode them as the only possible departments.
- Category is optional and represents a business grouping, not a permanent
  physical property.
- Brand is optional but meaningful when supplied. Never discard it.
- Material, color, and size/model participate in SKU identity.
- DTF clothing uses sizes. UV and most non-clothing products use models.
- Phone cases belong to department `UV` and category `手机壳`.

## Inventory

- UV daily consumption source is the private Google Sheet
  `https://docs.google.com/spreadsheets/d/1kbbexU-zePCPw5Rg5R2fJlcbnRLVFPYZQcL5U_Qoy7Y/edit`.
  The UV consumption model uses the latest 14 calendar days of synchronized
  movement data to show daily usage and connects matching SKUs to current
  inventory and the nearest container.
- UV Google Sheets are discovered from the shared Drive folder
  `1MhAq1n1dDd9P5WD0gdrR2uXH0Veb_MzA`. The daily-order workbook remains the
  default, while replacement workbooks placed in that folder can be selected
  without changing credentials or code.
- The UV plate-product category is named `铁板画`; material distinguishes
  `铁牌` and `铝牌`.
- Phone-case SKU material/model combinations come from the same
  `assets/dielines/phone_cases/catalog.json` catalog used by the phone-case
  image-processing page. Google Sheets supplies consumption facts, not the
  phone-case SKU master list.
- Current stock is supported by an immutable movement history.
- Normal warehouse daily outbound and temporary inventory adjustments are
  separate operation types, but both appear in unified SKU history.
- A batch must reconcile its displayed total with its saved database total.
- Missing or insufficient SKUs stop the entire batch and are shown to users.
- Direct table edits are temporary adjustments, not warehouse daily outbound.
- Opening inventory must create an auditable inbound movement.
- A SKU is "待初始化" when its quantity is zero and it has never had a positive
  inbound movement. A depleted SKU is not uninitialized.
- Different purchase batches may have different costs.
- Temporary transferred stock is consumed before normal bulk stock.
- Cost precision is four decimal places where supported.
- Consumables are counted and entered in boxes across the UI. The ledger keeps
  base-unit quantities internally and uses each SKU's required units-per-box
  conversion for accurate inventory arithmetic.
- Customer sales outbound is separate from warehouse production issue. It
  stores reusable company/person customer records, the seller company profile,
  an immutable Invoice header and priced SKU lines, and one linked inventory
  movement batch. Invoice issue and inventory deduction must commit in one
  database transaction so neither can exist without the other.
- Customer sales outbound is a standalone inventory navigation page, not a tab
  inside production inventory. Its reusable SKU selector follows the inventory
  identity dependency `material -> brand -> color -> size`; each downstream
  option is limited to active combinations that exist under the selections,
  and apparel sizes retain the business order `S` through `5XL`.
- Customer sales prices are entered for the sale and do not modify inventory
  cost. Issued Invoices retain seller/customer address snapshots through their
  linked records and remain downloadable from batch history. Corrections use
  an explicit void/reversal workflow rather than overwriting ledger history.
- A customer Invoice must follow `edit -> preview -> explicit confirmation ->
  issue`. Previewing never changes inventory. Any change to seller, customer,
  SKU, quantity, price, date, number, or note invalidates the preview and
  requires a new preview before the inventory transaction can be confirmed.

## Containers

- Container workflow:
  `添加货柜 -> 在途 -> 手动确认到柜 -> 确认入库`.
- The UI may combine arrival confirmation and inventory posting into one
  action for temporary or urgent arrivals, but the persisted state history
  must still record `在途 -> 已到柜 -> 已入库` and inventory is added once.
- Expected arrival is not actual arrival.
- Manual arrival confirmation records a date, which may be in the future.
- The confirmation operation time is recorded automatically in event history.
- Inventory changes only when container contents are confirmed into stock.
- Containers may belong to any department and use the same core workflow.
- Piece quantity is the accounting unit. Box/bag conversions are display and
  warehouse counting aids.
- Container forecasts should connect arriving SKUs with current stock risk.

## Production And QA

- Prefer Supabase summary functions over downloading daily detail rows.
- Filter by date and platform in the database, not after loading the full table.
- Haloo versus other clients is based on the database `platform`, not barcode
  patterns.
- QA uses `scanned_by`; hotstamp uses `hotstamp_by`.
- Daily boundaries and hourly analysis use New York time.
- Workflow switching analysis classifies each period as one platform group;
  a Haloo period cannot simultaneously report small-platform production.

## Garment Consumption Sources

### Unified Daily Consumption Operations

DTF consumables, black/white T-shirts, colored T-shirts, and UV production
inventory are four implementations of one daily-consumption operation. They
must share the operational contract even though their consumption models and
data-entry sources differ:

| Flow | Deduction input | Consumption model source |
| --- | --- | --- |
| DTF consumables | Warehouse staff enters actual boxes issued | Actual consumable issue ledger |
| Black/white T-shirts | Warehouse staff enters actual pieces or packaging issued | Actual warehouse daily outbound |
| Colored T-shirts | System reads synchronized production data | Colored-shirt production data |
| UV production inventory | System reads the configured Google Sheets source | Latest 14 days of valid Google Sheets data |

All four flows use the same user-facing operational concepts: New York
business date, daily preview, explicit confirmation, duplicate prevention,
auditable batch, operator and source attribution, current-stock result,
inventory ledger, SKU-level history, reversal/correction workflow, and
manager-readable daily status. “Manual” versus “system-read” must be visible
in the ledger and batch selector. System-read deductions must never be
presented as temporary manual outbound, and a system-read category must not
show a warehouse manual-outbound entry form.

The flows share an operational contract, not one user-facing name. Black/white
manual issues are `仓库每日出库`, consumables are `每日耗材出库`, and colored-shirt
or UV automation is `系统库存扣减`. The combined ledger filter is
`每日库存扣减`. Querying, history, status, permissions, audit, reversal, and
correction behavior still follow the shared contract. A source-specific
adapter may decide how rows are matched to SKUs and how the consumption model
is calculated; it must not create a second history or audit model.

One source and one business date must appear as one auditable ledger batch,
even when the source contains multiple categories or SKUs. The detail table
may contain many SKU rows, but the batch selector must not split one daily
sheet into several records.

The inventory module has one manager-facing `库存总结` workbench above the
individual production inventory, consumable inventory, and container pages.
It shows the completion count and missing business dates for every registered
daily-consumption flow. Manual sources link users to enter actual outbound;
system-readable sources are previewed and confirmed through one consolidated
operation. New automatic sources are registered in the shared automatic-flow
registry instead of adding another independent dashboard button.

For colored T-shirts, the system preview must list every configured production
platform with its read status and raw quantity. It also reconciles the raw
production total, the quantity mapped to deductible inventory, and the
unresolved difference. A missing platform or a nonzero difference blocks the
daily deduction so an incomplete day cannot be recorded as complete.

S2B production is read from the authenticated factory bill API, not from an
Excel export. The query uses the factory page's `production_at` field and a
New York business-day boundary from 00:00:00 through 23:59:59, reads every
page, verifies the returned row count, and then passes the rows through the
shared production catalog normalization. Browser export is only a manual
fallback for recovering an expired login; it is not the normal data path.

An aggregate production result must never present partial data as a generic
success. Show every configured platform as read or unread and preserve the
per-platform failure message in cache metadata. When an older partial cache
predates failure-message storage, explicitly say that its reason was not
recorded and direct the user to retry the missing platforms; do not invent a
cause or require all successful platforms to be fetched again.

The DTF production-inventory page must keep `仓库每日出库` visible when the
top-level category filter is `全部品类`. It also shows a separate
`系统库存扣减` entry for colored T-shirts. A required daily operation must not
disappear merely because a summary filter is broad, and system deductions
must never be presented as warehouse outbound.

A warehouse daily-outbound batch has exactly one business date. Users choose
`本批出库日期` once above the package/SKU table; row editors and downloaded
templates must not repeat the same date on every SKU row. The selected batch
date is applied to every saved movement in that batch.

Warehouse daily outbound must not write negative inventory. When an existing
SKU has insufficient stock, the outbound page may create a separate temporary
inventory-adjustment batch for the exact shortage and then keep the outbound
draft available for confirmation. This temporary batch must remain visible in
the ledger and reversible so the physical count can be corrected later. A
missing SKU is master-data work and must not be created implicitly by this
shortage flow.

Container arrival history separates filtering from presentation. The date
range limits which arrivals are included; users can then view one combined
table ordered by newest arrival time or group records by department, with each
department still ordered newest first.

Container arrival and inventory-posting confirmations are reversible user
workflows, not direct database fixes. Reversing a posting creates an inventory
batch reversal and returns the container to arrived; reversing arrival returns
it to the prior in-transit state and clears the actual-arrival fields. Original
events remain visible and a separate reversal event is appended. The UI must
require an explicit confirmation before either reversal.

All outbound domains follow the same reversal contract. Black/white T-shirt
warehouse outbound, colored T-shirt system deductions, UV system deductions,
temporary inventory movements, and DTF consumable issues keep their original
batch and append a reversing batch with operator and timestamp. Production
inventory and consumables may use separate ledgers, but neither may delete or
overwrite an effective outbound. The production-inventory reversal view uses
its own workflow/source filter and must not inherit stock-view date, category,
brand, material, color, or size filters.

The daily inventory-completion dashboard starts at 2026-08-01; dates before
that business baseline must not appear as missing work. Automatic flows load
all currently missing dates in one action, show a date-and-source preview with
quantities and blocking messages, and require one explicit confirmation before
applying every ready preview. Manual warehouse and consumable flows continue to
require actual reported quantities and must not invent a deduction merely to
fill a missing date.

The current New York business day is an in-progress day, not overdue work. Show
its completed and unfinished flows separately with a clear “today is not over”
message. Only dates through yesterday count as missing, appear in the automatic
backfill selector, or contribute to manager-facing overdue totals.

Corrections preserve the original batch. A manual-source correction reverses
the original and records a corrected replacement; a system-source correction
reverses the original and re-synchronizes the corrected source data. Neither
path directly overwrites movement history.

Incomplete production-platform data must not stop inventory/container
forecasting when at least one platform is available. The system estimates the
missing share using platform weights from the latest complete production
period and re-normalizes the available production to 100%. If no complete
history exists, it falls back to equal platform weights. The UI must list the
missing platforms, coverage percentage, scale factor, and clearly label the
forecast as an estimate.

- Black/white T-shirt inventory consumption is based primarily on actual
  warehouse daily outbound, not a direct SKU-for-SKU production deduction.
  Black/white volume is high, the SKU catalog is large, and warehouse staff may
  substitute an available size or SKU when the requested size is out of stock.
  Production data records the requested SKU and cannot reliably reveal that
  physical substitution, while warehouse outbound records what was actually
  issued. Production data may be used as a comparison or supporting model, but
  it must not silently replace warehouse outbound as the inventory truth.
- Colored T-shirt inventory consumption is based on production data and is
  deducted as a dated daily production batch. Its volume and SKU range are
  smaller, and different colored SKUs are not interchangeable. Warehouse daily
  outbound is therefore not required as the primary consumption source.
- UV inventory consumption is based on its Google Sheets production data and
  is deducted as a dated daily batch. Different UV SKUs are not interchangeable,
  so warehouse daily outbound is not required as the primary consumption
  source.
- A production-driven daily deduction never creates negative inventory. It
  deducts available stock down to zero and records the remaining demand as a
  counting/reconciliation difference. The full production quantity still
  participates in the consumption model, even when part of it could not be
  deducted because recorded stock was already zero.
- Container forecasting must use the consumption source appropriate to the
  category: warehouse-led consumption for black/white T-shirts, production-led
  consumption for colored T-shirts, and Google-Sheets-led consumption for UV.
  Missing production platforms may be shown as a data-quality warning for a
  production-led category, but available effective production days should still
  produce a forecast instead of stopping the entire calculation.

## Logistics Tracking

- Logistics acquisition reuses the production-data department and platform
  catalog. Users select department first and then a platform belonging to that
  department; do not maintain a separate hard-coded platform list.
- The initial logistics module is a pre-production shipping-label compliance
  review, not long-term delivery tracking.
- A pending-acceptance shipment is an ERP order that already has a tracking
  number but has no matching production acceptance, pre-scan, or QA scan in
  this system.
- Initial integration priority is SDS2, followed by the separate S2B UV and
  S2B DTF accounts. The connector contract must also support later SDS1,
  Yidian Wanxiang, 3D printing, and other ERP accounts without changing the
  shared shipment model.
- S2B exported workbooks include order code, merchant order number, shipping
  method, tracking number, order status, and production/shipping times. A
  successful automated S2B export must parse and persist those logistics fields
  immediately; users must not need to copy tracking numbers between pages.
- A compliant label must use the configured factory return address. The current
  factory street is `25 Ranic Road` and the state must be New York; the full
  normalized address belongs in company configuration rather than validation
  source code.
- Orders showing USPS pre-scan/pre-shipment or any later postal scan are not
  eligible for normal production acceptance. USPS is queried to establish
  scan activity at review time, not to monitor future delivery progress.
- Label weight is a required compliance check. Normal single-shirt labels are
  generally around 3-4 ounces or modestly above that range; pound-level labels
  such as 4 lb are suspicious and require investigation or rejection. Exact
  automatic pass, review, and reject thresholds must be configurable by
  company, product, and quantity.
- USPS Tracking does not supply the authoritative return address, label weight,
  or original label document. Download the label PDF from the ERP parcel data
  (`pdfUrl`/`laberPdf` or the equivalent connector field), preserve the source
  document, and extract address and weight from that document.
- Because many ERP platforms do not provide label downloads, USPS tracking
  events are the primary source for the label-creation origin city, state, and
  ZIP and must be preserved and shown in full. Use label OCR as a supplement
  for the street address and weight when a source document is available.
- USPS-format labels have a pickup-channel subtype. `CBT` is collected by the
  TikTok-designated logistics provider, while `CBS` is collected by GOFO.
  Prefer the ERP parcel `serviceProviderName` over the generic shipping-method
  name or tracking-number pattern when assigning this subtype. The logistics
  compliance database only imports ordinary USPS shipments; CBS and CBT are
  identified solely so they can be excluded from that workflow.
- Persist ERP account, platform, department, order ID, tracking number,
  carrier, label URL/file reference, label content hash, extracted return
  address, extracted weight, USPS scan result, rule version, compliance result,
  reviewer decision, and synchronization metadata.
- USPS checks are database-first because provider requests have a cost. Reuse a
  sufficiently fresh review-time result for the same tracking number, but
  revalidate when its cache expires, the label/tracking changes, the label hash
  changes, the compliance rules change, or an authorized reviewer requests a
  refresh.
- Record USPS usage separately from provider responses. Each live query event
  stores the submitted tracking-number count, HTTP batch count, success/failure
  totals, querying user, and New York reporting day. USPS usage events do not
  use a tenant placeholder; `created_by` identifies the user. Display today's usage, the
  current month's calibrated usage, remaining monthly allowance, percentage,
  and daily detail. The default monthly allowance is 100,000 and may be
  overridden per environment; an authorized user calibrates it against the
  USPS developer portal without storing response payloads.
- Store append-only provider-query and compliance-decision audit records.
  Repeated ERP synchronization, label downloads, and USPS responses must be
  idempotent and must not duplicate orders, documents, or review events.
- During the current workflow-validation phase, ERP shipment review remains
  live-only. Every tracking number actually submitted to USPS is persisted in
  `logistics_tracking_checks`, including the complete provider response,
  status flags, errors, querying user, query time, and cache expiration. The
  default lookup order is database first and USPS only for missing or expired
  records; authorized users may force a live USPS refresh.
- Cache downloaded label documents and OCR results in server memory by label
  URL for 24 hours during workflow validation. Repeated page refreshes and
  users on the same running server should reuse that cache; deployment or
  server restart may clear it because database persistence is not enabled yet.
- ERP synchronization only reads orders, tracking numbers, carrier decisions,
  and available label links. It must not automatically OCR normal shipments.
  Users select suspicious labels directly in the shared logistics review
  table; only those selected documents are downloaded and analyzed, and the
  results are reflected back into that same table. Completing OCR must refresh
  the editable-table state and the ordinary-USPS candidate context so newly
  extracted address, ounce/pound weight, and status are immediately visible.
- The shared logistics review supports manual selection, selecting every row
  with a downloadable label, and a user-sized random sample. Authorized users
  can also download all available label documents from the current review as
  one ZIP archive, independent of the active carrier filter.
- The default label-selection mode is selecting every downloadable label.
  Manual row selection is used only after the user explicitly switches to it.
- Seven Creation (`七创`) and Yiduoyun (`一朵云`) share the 19DIY ERP contract.
  Read their customer-order API by date and order stage and consume the order
  number, tracking number, carrier, and label URL directly; do not generate or
  parse an Excel export when those fields are already present in the response.
- ERP and USPS credentials are tenant/account configuration. Never copy tokens
  hard-coded in the legacy USPS project into application source.
- A local S2B connector must refresh a missing or expired account token through
  the project's dedicated Chrome session. It opens the normal S2B login and
  lets an administrator complete any required slider or human verification,
  then retries the API synchronization. Requiring a local user to configure a
  transient S2B token in Streamlit Secrets is not the normal local workflow.
- DTF, UV, and 3D use separate S2B accounts. Each account has an independent
  token, dedicated local Chrome profile, production cache scope, department,
  and ERP-account identity even though the shared platform name is S2B.

## Access

- The logistics tracking page is visible to supervisor, after-sales, and admin
  roles. Supervisors may query existing/database-cached and live USPS Tracking
  data, but only after-sales and admins may synchronize ERP data, run label
  OCR, download label batches, or calibrate USPS usage.
- User role assignment is available on a separate admin-only access-management
  page. Role changes and account activation changes require an explicit preview
  and confirmation, are written to an append-only audit trail, and must prevent
  an administrator from disabling or demoting their own account.
- Roles and role-permission composition are database-managed business records,
  not Python-defined business mappings. An access administrator can create a
  role and freely combine the registered permissions in the role-configuration
  tab. User assignment, permission matrices, login sessions, filters, and
  navigation use those persisted combinations. Every role creation or update
  stores before/after permission snapshots, operator, and timestamp.
- Visitor access requires no login.
- Supervisor inherits public visibility and can manage problem tracking.
- Producer focuses on production and consumable reporting.
- Warehouse manages inventory, consumables, and containers.
- After-sales can manage operational data except restricted cost information.
- Finance can view cost and finance reports but does not receive broad admin
  access automatically.
- Admin has all permissions and is the only role with unrestricted cost access.
- `utils/auth/constants.py` defines technical permission identifiers and page
  requirements only. Runtime role composition comes from `app_roles` and
  `app_role_permissions` in the database.
