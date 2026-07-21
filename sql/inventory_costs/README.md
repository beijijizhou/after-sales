# Inventory cost lot migration

Run these files in Supabase SQL Editor in order:

1. `01_cost_lot_schema.sql`
2. `02_adjustment_function.sql`
3. `03_reversal_function.sql`
4. `04_cost_reporting.sql`
5. `../inventory_sku_updates.sql`

After installation, run `05_verify_cost_lots.sql`. Its first query must return
no rows.

Run `06_four_decimal_costs.sql` to upgrade every active inventory unit-cost
column from two decimal places to four decimal places.

The migration keeps `inventory_items.unit_cost` for compatibility. Cost history
is stored in `inventory_cost_lots`, while outbound deductions are stored in
`inventory_cost_allocations`.

Outbound allocation always consumes `transfer` stock first. Within the same
source type, the oldest lot is consumed first.
