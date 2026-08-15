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

- Consumables are an independent inventory domain. Production inventory and
  production SKU management must not expose consumable categories or embed
  consumable operations. The consumables page owns current stock, daily issue,
  inbound, inventory setting, ledger, reversal, and consumable SKU management,
  while preserving the same review and audit concepts used by production
  inventory.
- A consumable name represents the reusable product identity, while brand and
  specification/model may vary by SKU. Creating a similar consumable SKU may
  copy category, consumable name, base unit, and package unit from an existing
  SKU, then require the user to review specification, brand, units per box, and
  minimum stock before saving.

- UV daily consumption source is the private Google Sheet
  `https://docs.google.com/spreadsheets/d/1kbbexU-zePCPw5Rg5R2fJlcbnRLVFPYZQcL5U_Qoy7Y/edit`.
  The UV consumption model uses the latest 14 calendar days of synchronized
  movement data to show daily usage and connects matching SKUs to current
  inventory and the nearest container.
- UV Google Sheets are discovered from the shared Drive folder
  `1MhAq1n1dDd9P5WD0gdrR2uXH0Veb_MzA`. The daily-order workbook remains the
  default, while replacement workbooks placed in that folder can be selected
  without changing credentials or code.
- Google Sheets product `Iphone` represents phone-case production and is
  intentionally excluded from UV inventory statistics and deductions until a
  model-level phone-case allocation exists. Every batch backfill preview must
  show its excluded quantity explicitly; it must not be silently absorbed into
  the displayed source or confirmation total.
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
- A one-time inventory brand reclassification is not a SKU master-data merge.
  It moves a confirmed quantity from existing source-brand SKUs to matching
  target-brand SKUs as one auditable, inventory-neutral batch. Source SKUs
  remain active for future inbound and outbound, historical movements retain
  their original brands, and the batch records source, target, quantity,
  operator, business date, and before/after balances. Do not turn a single
  reclassification into a permanent cross-brand aggregation rule or rewrite
  all historical SKU identities.
- A persistent SKU merge is a separate, explicit master-data rule. It may
  route one source brand group into a target brand only when department,
  category, material, color, and size semantics remain compatible. Activating
  the rule atomically transfers current quantity, warehouse distribution, and
  open cost lots; creates any missing target-size SKU; leaves historical
  movements unchanged; sets the source SKU quantity to zero and makes it
  inactive; and records both a batch audit and the active source-to-target
  rule. Future container inbound using the source identity is routed to the
  target. The SKU-management UI must show the active rule and a size-level
  before/source/target/after preview before confirmation.
- Manual inventory adjustment has three explicit actions: increase, decrease,
  and set. `Set` is a physical-count operation: the entered number is the
  target balance, while the system preserves the prior balance, target,
  calculated signed difference, operator, business date, and resulting balance
  in a batch-first audit record.
- Opening inventory must create an auditable inbound movement.
- A SKU is "待初始化" when its quantity is zero and it has never had a positive
  inbound movement. A depleted SKU is not uninitialized.
- Different purchase batches may have different costs.
- Temporary transferred stock is consumed before normal bulk stock.
- Cost precision is four decimal places where supported.
- Consumables with a configured box rule are counted and entered in boxes.
  When a SKU genuinely has no box rule, the UI records and displays its base
  unit (for example pieces or meters) without inventing a conversion. The
  ledger always keeps base-unit quantities internally.
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
- Colored T-shirt inventory defaults to the manager-facing and customer-facing
  identity `material -> color -> size`, with all brands combined. The active
  brand-handling rule must be visible in the UI: users may switch sales to
  brand-specific outbound and inventory to brand-detail viewing. Under the
  default combined rule, the system allocates a confirmed deduction across the
  real brand SKUs underneath and keeps those brands in movement history for
  audit, correction, and traceability.
- The default colored T-shirt combined inventory table is a manager screenshot
  view: it stretches to the available page width, keeps apparel sizes in
  `S -> 5XL` order, uses compact columns, and expands vertically to show the
  available rows without routine scrolling.
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
- New container line items must be created through the shared dependent SKU
  identity order `category -> material -> brand -> color -> size/model`.
  Changing material immediately limits or resets brand and every downstream
  field to combinations present in the active SKU catalog. The resulting wide
  quantity table locks identity fields so invalid combinations cannot be typed
  back into the batch.

## Warehouses And Transfers

- The active warehouses are `25`, `60`, and `70`. Warehouse `25` is the
  default operational warehouse for garment outbound and may also store stock;
  warehouses `60` and `70` primarily store reserve inventory.
- `inventory_items` remains the authoritative company-wide SKU total and cost
  record. Warehouse balances describe physical distribution underneath that
  total. Moving stock between warehouses never changes company-wide quantity
  or cost.
- Existing inventory is assigned to warehouse `25` when warehouse distribution
  is first initialized. Normal inventory movements default to warehouse `25`
  and synchronize that distribution balance. The distribution table must show
  25/60/70, in-transit or unresolved quantities, and any difference from the
  company total so drift is visible rather than hidden.
- Locations are optional reference notes, not strict inventory identity and
  never block inbound, outbound, or transfer. Examples include `A区`, `靠门`,
  or `第二托`.
- A shortage-restock request selects the target SKUs but does not require a
  requested quantity. Actual quantities are recorded only after warehouse
  staff find and dispatch stock. The lightweight states are `待配货 -> 运输中
  -> 已收到`; an immediate physical move may use `直接完成调拨` while retaining
  the same atomic batch record.
- Dispatch subtracts the actual quantity from the source warehouse and exposes
  it as in transit. Receipt adds the actual received quantity to the target
  warehouse. Differences remain visible as `在途/待核对`. Every transfer keeps
  its source and target warehouses, SKU targets, actual sent and received
  quantities, optional locations, operators, timestamps, and status.

## Production And QA

## Platform Finance

- Platform financial corrections use a read, reconcile, preview and export
  workflow. A corrected price calculation must preserve the provider's
  original order line, material fee, other fees, refunds and total alongside
  the proposed price rule, recalculated material fee and difference. A preview
  or export never silently writes revised amounts back to the provider.
- Provider customer-group IDs, when used, and credentials are tenant
  configuration, not shared source constants. A blank customer-group filter
  reads every customer in the selected tenant and date range. Financial
  acquisition must read every page, dedupe stable order/SKU identities and
  show unmatched price rules before users rely on the recalculated total.
- Fangguo reconciliation prices default to one price per product/material for
  the current Haloo and Longfeng accounts. The operator may explicitly switch
  to product-and-model pricing when models need different prices. Color and
  provider SKU specification remain traceability fields and never split the
  price rule. The result produces separate Haloo and Longfeng bills, with
  Longfeng 1/2/3 consolidated and every bill retaining its order numbers,
  original amount, corrected amount and amount still due.
- Each customer-facing Bill is one Excel workbook: the first worksheet is the
  concise product summary and the second is the provider order detail. The UI
  does not emit separate recalculation or order-detail CSV files for the same
  Bill.

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

DTF consumables now follow the same manager-facing planning pattern as
production inventory: the consumables page exposes both a `点货预测` view and a
`消耗模型` view. The consumable consumption model is built only from effective
`issue` batches in the consumable ledger for the recent lookback window, using
New York business dates and excluding reversed batches or reversed movement
rows. The first reorder forecast uses that recent average daily issue quantity
as the system daily usage and combines it with each SKU's current stock and
`minimum_quantity` safety threshold to show coverage days, earliest depletion
date, and suggested reorder quantity. Until procurement lead time or target
coverage is stored in master data, the forecast uses the operator-selected
target coverage days from the UI instead of an implicit hard-coded SKU rule.

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

Every daily-consumption flow also uses one shared forecasting shape. The core
daily-usage engine must not diverge by category or SKU. Source adapters may
only normalize upstream facts into daily usage events and define which dates
count as observable business dates; they must not introduce a separate
averaging formula, a separate reorder contract, or a second forecasting math
path for one department. The shared output therefore keeps the same concepts
across DTF consumables, black/white T-shirts, colored T-shirts, and UV
production inventory: window total usage, effective data days, natural window
days, effective-day average usage, and natural-window average usage. A page
may choose which shared metric is its active planning basis, but that choice
must stay explicit in the UI and must reuse the same core engine.

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

Colored T-shirt quick backfill requires `汉森`, `S2B`, `SDS1`, `SDS2`,
`Haloo`, and `隆丰`. Haloo and Longfeng use their configured Humbird Open API
keys through the shared production adapter. Other low-volume platforms do not
block quick backfill; the production-data page remains responsible for the
complete all-platform reconciliation.

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
- ERP logistics synchronization must show live, platform-specific progress for
  connection, order/label retrieval, persistence, carrier classification, and
  USPS candidate preparation; a completion-only summary is not sufficient.
  Concurrent platforms must each keep one stable row in the progress table and
  update only their own latest status and result metrics. Do not interleave
  platform steps into one chronological text log.
- ERP logistics dates default to the current day for both start and end. Users
  may widen the range for historical review. Independent selected platforms
  are fetched concurrently with a user-selected one-to-eight workers, default
  four. This control does not run OCR. After the selected reads finish,
  persistence follows fetch-completion order instead of platform selection
  order.
- ERP logistics classifies carrier and USPS pickup subtype before persistence.
  ERP acquisition and OCR never create shipment rows. Only ordinary USPS
  relationships whose tracking number has an official USPS Tracking API check
  are stored in `logistics_shipments`. GOFO, CBS, CBT and other carriers remain
  available for the current carrier review but are not persisted or included
  in logistics summary details.
- ERP logistics uses three shared business stages: `未接单` means no production
  batch exists, `已接单（生产中）` means a batch exists, and `已发货` means the
  order completed production and quality inspection; an ERP may label the same
  state `已生产`. A shipping label can exist before this stage and is not the
  stage definition. Connector-specific status codes must map into these terms;
  Humbird `status=9` maps to the completed `已生产/已发货` stage.
- S2B logistics date scope must be sent to the ERP and verified again after the
  response. Use assignment time for `未接单`, confirmation/production-plan time
  for `已接单（生产中）`, and production-completion time for `已发货`. Never
  treat all historical rows in an order status as the selected date range.
  S2B accepts 1,000 orders per page, so the connector uses that verified page
  size instead of issuing ten 100-row calls for the same data.
- The current 3D department scope contains only its independent S2B account and
  the SDS `3D热转印` profile. Do not expose other ERP platforms under 3D until
  the business explicitly enables them.
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
- Every successful ERP logistics read and validated manual order/tracking import
  persists the order-to-tracking relationship immediately, including department,
  platform, ERP account and every available primary or backup label PDF URL.
  A USPS query keeps a many-to-many source snapshot so one provider request is
  counted once even when its tracking number belongs to multiple ERP orders.
- The logistics data summary is batch-first by New York business date,
  department, platform and ERP account. It shows ERP orders, distinct tracking
  numbers, USPS query counts, PDF coverage and OCR coverage before users select
  one summary row to inspect order-level activity. OCR attempts are append-only
  review records containing the source PDF, content hash, extracted address,
  ounce weight, engine version, operator, status, error and timestamp.
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
