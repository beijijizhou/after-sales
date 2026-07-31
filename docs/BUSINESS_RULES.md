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

## Access

- Visitor access requires no login.
- Supervisor inherits public visibility and can manage problem tracking.
- Producer focuses on production and consumable reporting.
- Warehouse manages inventory, consumables, and containers.
- After-sales can manage operational data except restricted cost information.
- Finance can view cost and finance reports but does not receive broad admin
  access automatically.
- Admin has all permissions and is the only role with unrestricted cost access.
- Permission composition is defined in `utils/auth/constants.py`.
