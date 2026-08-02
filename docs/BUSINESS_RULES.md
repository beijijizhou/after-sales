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
- Store append-only provider-query and compliance-decision audit records.
  Repeated ERP synchronization, label downloads, and USPS responses must be
  idempotent and must not duplicate orders, documents, or review events.
- During the current workflow-validation phase, ERP shipment review and USPS
  tracking queries are live-only and are not persisted by the logistics page.
- Cache downloaded label documents and OCR results in server memory by label
  URL for 24 hours during workflow validation. Repeated page refreshes and
  users on the same running server should reuse that cache; deployment or
  server restart may clear it because database persistence is not enabled yet.
- ERP synchronization only reads orders, tracking numbers, carrier decisions,
  and available label links. It must not automatically OCR normal shipments.
  Users select suspicious labels directly in the shared logistics review
  table; only those selected documents are downloaded and analyzed, and the
  results are reflected back into that same table.
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

## Access

- The logistics tracking and shipping-label review page is restricted to the
  after-sales and admin roles. Other roles must not see its navigation entry or
  access it by direct URL.
- Visitor access requires no login.
- Supervisor inherits public visibility and can manage problem tracking.
- Producer focuses on production and consumable reporting.
- Warehouse manages inventory, consumables, and containers.
- After-sales can manage operational data except restricted cost information.
- Finance can view cost and finance reports but does not receive broad admin
  access automatically.
- Admin has all permissions and is the only role with unrestricted cost access.
- Permission composition is defined in `utils/auth/constants.py`.
