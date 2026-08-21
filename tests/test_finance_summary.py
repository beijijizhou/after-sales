import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from db.finance.summary import (
    build_container_summary,
    build_daily_summary,
    build_department_summary,
    build_finance_overview,
    build_inventory_value_overview,
)
from db.finance.repository import (
    _exclude_stocktake_batches,
    _normalize_cost_rows,
    normalize_consumable_finance_rows,
)
from ui.inventory.stock.batch_costs import (
    build_cost_batch_summary,
    build_missing_cost_batch_overview,
    build_missing_cost_groups,
    build_previous_brand_cost_preview,
    build_reference_cost_preview,
    find_cost_changes,
    latest_material_cost_source,
    match_previous_brand_costs,
    resolve_pasted_cost_targets,
    filter_cost_history_scope,
)
from db.inventory.core.costs import fill_missing_inventory_group_costs
from ui.finance.cost_catalog import (
    build_sku_cost_history,
    build_sku_cost_overview,
)
from ui.finance.inbound_batches import build_inbound_batch_summary
from ui.finance.pending_costs import build_pending_cost_batch_summary
from ui.finance.page import _build_two_week_daily_amounts
from ui.finance.reports import build_missing_cost_scope_summary
from ui.inventory.stock.cost_summary import build_sku_price_completion
import ui.finance.page as finance_page
from utils.auth.constants import NAV_SECTIONS, ROLE_PERMISSIONS


class FinanceSummaryTests(unittest.TestCase):
    def setUp(self):
        self.finance = pd.DataFrame([
            {
                "date": "2026-07-01", "direction": "入库",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 100, "amount": 130, "missing_cost": False,
            },
            {
                "date": "2026-07-02", "direction": "出库",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 40, "amount": 52, "missing_cost": False,
            },
            {
                "date": "2026-07-02", "direction": "出库",
                "department": "UV", "category": "铁板画",
                "quantity": 5, "amount": 0, "missing_cost": True,
            },
        ])

    def test_overview_separates_inbound_and_outbound(self):
        result = build_finance_overview(self.finance)
        self.assertEqual(result["inbound_quantity"], 100)
        self.assertEqual(result["outbound_quantity"], 45)
        self.assertEqual(result["outbound_amount"], 52)
        self.assertEqual(result["missing_outbound_quantity"], 5)

    def test_finance_page_defaults_to_lazy_inbound_batch_loading(self):
        empty = pd.DataFrame()
        spinner = MagicMock()
        spinner.__enter__.return_value = None
        spinner.__exit__.return_value = None
        with (
            patch.object(finance_page, "_render_month_selector", return_value=date(2026, 8, 1)),
            patch.object(finance_page.st, "radio", return_value="入库批次"),
            patch.object(finance_page.st, "spinner", return_value=spinner),
            patch.object(finance_page, "load_inventory_finance_month", return_value=empty) as finance,
            patch.object(finance_page, "load_pending_cost_batches", return_value=empty) as pending,
            patch.object(finance_page, "load_inventory_value_snapshot") as snapshot,
            patch.object(finance_page, "load_inbound_cost_history") as history,
            patch.object(finance_page, "load_container_finance_month") as containers,
            patch.object(finance_page, "_render_inbound_batches") as render,
        ):
            finance_page.render_finance_page(object())
        finance.assert_called_once()
        pending.assert_called_once()
        render.assert_called_once()
        snapshot.assert_not_called()
        history.assert_not_called()
        containers.assert_not_called()

    def test_stocktake_batches_are_not_reported_as_purchase_inbound(self):
        rows = pd.DataFrame([
            {"batch_id": "stocktake-a", "quantity": 18563},
            {"batch_id": "purchase-a", "quantity": 10800},
        ])

        class Query:
            data = [{"batch_id": "stocktake-a"}]

            def select(self, *_args): return self
            def in_(self, *_args): return self
            def execute(self): return self

        class Supabase:
            def table(self, name):
                self.table_name = name
                return Query()

        result = _exclude_stocktake_batches(Supabase(), rows)
        self.assertEqual(result["batch_id"].tolist(), ["purchase-a"])

    def test_pending_cost_batch_is_one_wide_row_in_size_order(self):
        rows = pd.DataFrame([
            {
                "id": f"row-{size}", "business_date": "2026-08-12",
                "department": "DTF", "category": "彩色短袖",
                "brand": "Daisy", "material": "180g", "color": "黄色",
                "size": size, "quantity": quantity, "unit_cost": cost,
                "inventory_effect": "not_posted", "status": "ready_to_allocate",
                "note": "发票 26081001", "created_by": "Andy",
            }
            for size, quantity, cost in [
                ("S", 490, 1.6), ("M", 490, 1.6), ("L", 490, 1.6),
                ("XL", 350, 1.6), ("2XL", 235, 2.1), ("3XL", 117, 2.1),
            ]
        ])
        result = build_pending_cost_batch_summary(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["总件数"], 2172)
        self.assertEqual(result.iloc[0]["总金额"], 3651.2)
        self.assertEqual(result.iloc[0]["S"], "490 × $1.6000")
        self.assertEqual(result.iloc[0]["3XL"], "117 × $2.1000")
        self.assertEqual(result.iloc[0]["4XL"], "")

    def test_inventory_value_overview_uses_current_remaining_value(self):
        snapshot = pd.DataFrame([
            {
                "inventory_quantity": 100,
                "inventory_value": 138,
                "missing_cost_quantity": 0,
            },
            {
                "inventory_quantity": 50,
                "inventory_value": 20,
                "missing_cost_quantity": 10,
            },
        ])
        result = build_inventory_value_overview(snapshot)
        self.assertEqual(result["inventory_quantity"], 150)
        self.assertEqual(result["inventory_value"], 158)
        self.assertEqual(result["missing_cost_quantity"], 10)

    def test_missing_cost_scope_summary_shows_where_to_fix(self):
        rows = pd.DataFrame([
            {
                "department": "UV", "category": "铁板画",
                "missing_cost_quantity": 70000,
            },
            {
                "department": "UV", "category": "铁板画",
                "missing_cost_quantity": 2000,
            },
            {
                "department": "DTF", "category": "彩色短袖",
                "missing_cost_quantity": 578,
            },
            {
                "department": "DTF", "category": "黑白短袖",
                "missing_cost_quantity": 0,
            },
        ])

        result = build_missing_cost_scope_summary(rows)

        self.assertEqual(result.iloc[0].to_dict(), {
            "部门": "UV", "品类": "铁板画", "缺成本库存": 72000,
        })
        self.assertEqual(result.iloc[1]["缺成本库存"], 578)

    def test_department_summary_calculates_net_change(self):
        result = build_department_summary(self.finance)
        dtf = result[result["部门"] == "DTF"].iloc[0]
        self.assertEqual(dtf["库存数量净变动"], 60)
        self.assertEqual(dtf["成本净增加"], 78)

    def test_daily_summary_keeps_both_directions(self):
        result = build_daily_summary(self.finance)
        second_day = result.iloc[1]
        self.assertEqual(second_day["出库数量"], 45)
        self.assertEqual(second_day["入库数量"], 0)

    def test_two_week_daily_amounts_has_date_labels_and_zero_days(self):
        result = _build_two_week_daily_amounts(
            self.finance, date(2026, 7, 14)
        )
        self.assertEqual(len(result), 14)
        self.assertEqual(result.iloc[0]["日期"], "07/01")
        self.assertEqual(result.iloc[-1]["日期"], "07/14")
        self.assertEqual(result.iloc[1]["出库成本"], 52)
        self.assertEqual(result.iloc[-1]["入库金额"], 0)

    def test_container_summary_groups_size_rows(self):
        source = pd.DataFrame([
            {
                "container_key": "A", "container_no": "A",
                "expected_arrival_date": "2026-07-29",
                "actual_arrival_date": None, "status": "未到货",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 60, "amount": 78, "missing_cost": False,
            },
            {
                "container_key": "A", "container_no": "A",
                "expected_arrival_date": "2026-07-29",
                "actual_arrival_date": None, "status": "未到货",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 40, "amount": 52, "missing_cost": False,
            },
        ])
        result = build_container_summary(source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["数量"], 100)
        self.assertEqual(result.iloc[0]["采购金额"], 130)

    def test_inbound_date_comes_from_cost_lot(self):
        rows = [{
            "id": "lot-a",
            "inbound_movement_id": "movement-a",
            "received_quantity": 10,
            "unit_cost": 1.3,
            "source_type": "bulk",
            "movement_date": "2026-07-29",
            "inventory_items": {
                "department": "DTF",
                "category": "黑白短袖",
                "brand": "Men's",
                "material": "160g",
                "color": "黑",
                "size": "S",
            },
        }]
        result = _normalize_cost_rows(
            rows,
            "inventory_items",
            "received_quantity",
            "入库",
            date_column="movement_date",
        )
        self.assertEqual(str(result.iloc[0]["date"]), "2026-07-29")
        self.assertEqual(result.iloc[0]["amount"], 13)

    def test_consumable_finance_uses_latest_cost_for_outbound(self):
        departments = pd.DataFrame([{"id": "d1", "code": "DTF"}])
        items = pd.DataFrame([{
            "id": "i1", "department_id": "d1", "category": "墨水",
            "name": "白色墨水", "specification": "", "brand": "",
            "base_unit": "瓶", "package_unit": "箱",
            "units_per_package": 20, "current_quantity": 720,
        }])
        batches = pd.DataFrame([
            {
                "id": "b-out", "department_id": "d1",
                "movement_type": "issue", "reversal_of_batch_id": None,
            },
            {
                "id": "b-in", "department_id": "d1",
                "movement_type": "inbound", "reversal_of_batch_id": None,
            },
        ])
        movements = pd.DataFrame([
            {
                "id": "m-out", "batch_id": "b-out", "item_id": "i1",
                "movement_date": "2026-08-06", "quantity_change": -120,
                "unit_cost": None, "created_at": "2026-08-06T12:00:00Z",
            },
            {
                "id": "m-in", "batch_id": "b-in", "item_id": "i1",
                "movement_date": "2026-08-07", "quantity_change": 840,
                "unit_cost": 10, "created_at": "2026-08-07T12:00:00Z",
            },
        ])

        result = normalize_consumable_finance_rows(
            departments, items, batches, movements,
            date(2026, 8, 1), date(2026, 9, 1),
        )

        outbound = result[result["direction"] == "出库"].iloc[0]
        self.assertEqual(outbound["category"], "DTF耗材")
        self.assertEqual(outbound["material"], "墨水")
        self.assertEqual(outbound["color"], "白色墨水")
        self.assertEqual(outbound["unit_cost"], 10)
        self.assertEqual(outbound["amount"], 1200)
        self.assertFalse(outbound["missing_cost"])

    def test_inbound_cost_batches_group_skus_and_show_latest_first(self):
        rows = pd.DataFrame([
            _finance_inbound(
                "lot-2030", "batch-today", "2030", 26400, 0.607,
                "2026-08-06T22:30:00+00:00",
            ),
            _finance_inbound(
                "lot-1040", "batch-today", "1040", 10800, 0.607,
                "2026-08-06T22:30:01+00:00",
            ),
            _finance_inbound(
                "lot-old", "batch-old", "2030", 1000, 0.41,
                "2026-08-05T12:00:00+00:00",
            ),
        ])

        result = build_inbound_batch_summary(rows)

        self.assertEqual(result["批次号"].tolist(), ["batch-today", "batch-old"])
        self.assertEqual(result.iloc[0]["SKU数"], 2)
        self.assertEqual(result.iloc[0]["数量"], 37200)
        self.assertAlmostEqual(result.iloc[0]["金额"], 22580.4)

    def test_container_business_batch_groups_inventory_and_consumables(self):
        inventory = _finance_inbound(
            "lot", "inventory-batch", "2030", 65000, 0.2406,
            "2026-08-11T22:00:00+00:00",
        )
        consumable = _finance_inbound(
            "movement", "consumable-batch", "24×32+4cm", 25410,
            0.0403, "2026-08-11T22:01:00+00:00",
        )
        for row, domain, unit in [
            (inventory, "生产库存", "件"),
            (consumable, "耗材库存", "件"),
        ]:
            row.update({
                "business_batch_key": "货柜:12柜",
                "business_batch_label": "12柜｜柜号 ZCSU7707166",
                "inventory_domain": domain,
                "quantity_unit": unit,
            })

        result = build_inbound_batch_summary(
            pd.DataFrame([inventory, consumable])
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["批次名称"], "12柜｜柜号 ZCSU7707166")
        self.assertEqual(result.iloc[0]["生产库存数量"], 65000)
        self.assertEqual(result.iloc[0]["耗材项数"], 1)

    def test_finance_dashboard_is_admin_only(self):
        self.assertIn(
            "can_view_finance_dashboard", ROLE_PERMISSIONS["admin"]
        )
        for role, permissions in ROLE_PERMISSIONS.items():
            if role != "admin":
                self.assertNotIn(
                    "can_view_finance_dashboard", permissions
                )

    def test_cost_editor_only_returns_changed_positive_costs(self):
        original = pd.DataFrame([
            {"批次ID": "a", "单位成本": None},
            {"批次ID": "b", "单位成本": 1.3},
            {"批次ID": "c", "单位成本": 2.0},
        ])
        edited = pd.DataFrame([
            {"批次ID": "a", "单位成本": 2.12},
            {"批次ID": "b", "单位成本": 1.3},
            {"批次ID": "c", "单位成本": 0},
        ])
        self.assertEqual(find_cost_changes(original, edited), [("a", 2.12)])

    def test_cost_catalog_lists_zero_price_as_missing_and_keeps_history(self):
        values = pd.DataFrame([{
            "department": "UV", "category": "铁板画", "brand": "",
            "material": "铁牌", "color": "白", "size": "2030",
            "inventory_quantity": 100000, "tracked_quantity": 15000,
            "inventory_value": 3000, "missing_cost_quantity": 85000,
        }])
        history = pd.DataFrame([
            {
                "record_id": "lot-1", "batch_id": "batch-1",
                "business_batch_label": "第十一柜｜柜号 HAMU4767628",
                "date": "2026-08-05", "recorded_at": "2026-08-05T12:00:00Z",
                "direction": "入库", "department": "UV", "category": "铁板画",
                "brand": "", "material": "铁牌", "color": "白", "size": "2030",
                "quantity": 85000, "unit_cost": 0, "source_type": "bulk",
            },
            {
                "record_id": "lot-2", "batch_id": "batch-2",
                "business_batch_label": "第九柜",
                "date": "2026-07-20", "recorded_at": "2026-07-20T12:00:00Z",
                "direction": "入库", "department": "UV", "category": "铁板画",
                "brand": "", "material": "铁牌", "color": "白", "size": "2030",
                "quantity": 15000, "unit_cost": 0.2, "source_type": "bulk",
            },
        ])

        overview = build_sku_cost_overview(values, history)
        detail = build_sku_cost_history(history, overview.iloc[0]["sku_key"])

        self.assertEqual(overview.iloc[0]["cost_status"], "缺成本")
        self.assertEqual(overview.iloc[0]["missing_batches"], 1)
        self.assertEqual(overview.iloc[0]["latest_cost"], 0.2)
        self.assertEqual(detail.iloc[0]["批次"], "第十一柜｜柜号 HAMU4767628")
        self.assertEqual(detail.iloc[0]["成本状态"], "缺成本")

    def test_cost_batches_group_legacy_opening_skus(self):
        rows = pd.DataFrame([
            {
                **_finance_inbound(
                    "opening-2xl", None, "2XL", 2000, 0,
                    "2026-08-06T12:00:00+00:00",
                ),
                "source_type": "opening", "unit_cost": None,
            },
            {
                **_finance_inbound(
                    "opening-3xl", None, "3XL", 2000, 0,
                    "2026-08-06T12:00:01+00:00",
                ),
                "source_type": "opening", "unit_cost": None,
            },
        ])
        result = build_cost_batch_summary(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["SKU数"], 2)
        self.assertEqual(result.iloc[0]["数量"], 4000)
        self.assertEqual(result.iloc[0]["缺成本SKU"], 2)

    def test_reference_cost_fill_groups_only_missing_cost_batches(self):
        rows = pd.DataFrame([
            _dtf_cost_row(
                "missing-l", "batch-a", "Haloo", "180g", "白", "L",
                2000, None, "2026-08-10",
            ),
            _dtf_cost_row(
                "missing-xl", "batch-a", "Haloo", "180g", "白", "XL",
                1600, 0, "2026-08-10",
            ),
            _dtf_cost_row(
                "priced-2xl", "batch-b", "Haloo", "180g", "白", "2XL",
                1500, 1.67, "2026-08-09",
            ),
        ])

        result = build_missing_cost_groups(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["缺成本批次"], 1)
        self.assertEqual(result.iloc[0]["缺成本记录"], 2)
        self.assertEqual(result.iloc[0]["缺成本数量"], 3600)

    def test_reference_cost_uses_latest_price_in_selected_business_scope(self):
        rows = pd.DataFrame([
            _dtf_cost_row(
                "cvc-old", "batch-old", "Haloo", "CVC", "黑", "S",
                1000, 0.88, "2026-08-05",
            ),
            _dtf_cost_row(
                "cvc-current", "batch-current", "Haloo", "CVC", "黑", "M",
                1000, 0.9182, "2026-08-06",
            ),
            {
                **_dtf_cost_row(
                    "uv-cvc", "uv-batch", "", "CVC", "白", "2030",
                    1000, 9.99, "2026-08-07",
                ),
                "department": "UV", "category": "铁板画",
            },
        ])

        source = latest_material_cost_source(
            rows, "CVC", department="DTF", category="黑白短袖"
        )

        self.assertEqual(source["日期"], date(2026, 8, 6))
        self.assertAlmostEqual(source["单位成本"], 0.9182)

    def test_reference_cost_preview_is_wide_and_preserves_existing_cost(self):
        rows = pd.DataFrame([
            _dtf_cost_row(
                "missing-s", "batch-a", "SK", "180g", "黑", "S",
                1200, None, "2026-08-10",
            ),
            _dtf_cost_row(
                "missing-3xl", "batch-a", "SK", "180g", "黑", "3XL",
                500, 0, "2026-08-10",
            ),
            _dtf_cost_row(
                "priced-xl", "batch-a", "SK", "180g", "黑", "XL",
                700, 1.67, "2026-08-10",
            ),
        ])
        key = build_missing_cost_groups(rows).iloc[0]["目标键"]

        preview, lots = build_reference_cost_preview(rows, [key], 0.9182)

        self.assertEqual(lots["record_id"].tolist(), ["missing-s", "missing-3xl"])
        self.assertEqual(preview.iloc[0]["S"], 1200)
        self.assertEqual(preview.iloc[0]["XL"], 0)
        self.assertEqual(preview.iloc[0]["3XL"], 500)
        self.assertEqual(preview.iloc[0]["总件数"], 1700)
        self.assertAlmostEqual(preview.iloc[0]["补价金额"], 1560.94)

    def test_reference_cost_targets_can_be_pasted_as_business_dimensions(self):
        rows = pd.DataFrame([
            _dtf_cost_row(
                "haloo", "batch-a", "Haloo", "180g", "白", "S",
                100, None, "2026-08-10",
            ),
            _dtf_cost_row(
                "misc", "batch-b", "杂牌", "160g", "白", "M",
                200, None, "2026-08-10",
            ),
        ])
        groups = build_missing_cost_groups(rows)

        selected, unmatched = resolve_pasted_cost_targets(
            "Haloo 180g 白\n杂牌｜160g｜白\n不存在 160g 黑", groups
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(unmatched, ["不存在 160g 黑"])

    def test_inventory_cost_batch_scope_follows_department_and_category(self):
        rows = pd.DataFrame([
            _dtf_cost_row(
                "dtf", "batch-a", "Haloo", "CVC", "黑", "S",
                100, 0.9182, "2026-08-10",
            ),
            {
                **_dtf_cost_row(
                    "uv", "batch-b", "", "铁牌", "白", "2030",
                    200, 0.2, "2026-08-10",
                ),
                "department": "UV", "category": "铁板画",
            },
        ])

        scoped = filter_cost_history_scope(rows, "DTF", "黑白短袖")

        self.assertEqual(scoped["record_id"].tolist(), ["dtf"])

    def test_missing_cost_batch_overview_lists_skus_batch_first(self):
        rows = pd.DataFrame([
            {
                **_dtf_cost_row(
                    "missing-l", "batch-a", "", "木板", "白", "2030",
                    5000, None, "2026-07-30",
                ),
                "department": "UV", "category": "木板画",
                "business_batch_label": "木板临时入库",
            },
            {
                **_dtf_cost_row(
                    "missing-cup", "batch-b", "", "直杯", "", "600ML",
                    5000, None, "2026-07-30",
                ),
                "department": "UV", "category": "保温杯",
                "business_batch_label": "杯子临时入库",
            },
            {
                **_dtf_cost_row(
                    "priced", "batch-c", "", "铁牌", "白", "2030",
                    1000, 0.211, "2026-08-20",
                ),
                "department": "UV", "category": "铁板画",
            },
        ])

        result = build_missing_cost_batch_overview(rows)

        self.assertEqual(result["批次"].tolist(), ["木板临时入库", "杯子临时入库"])
        self.assertEqual(result.iloc[0]["缺成本 SKU"], "木板｜白｜2030")
        self.assertEqual(result.iloc[0]["批次数量"], 5000)
        self.assertNotIn("铁牌｜白｜2030", "；".join(result["缺成本 SKU"]))

    def test_sku_price_completion_counts_active_skus_only(self):
        rows = pd.DataFrame([
            {"id": "priced", "quantity": 100, "unit_cost": 0.22},
            {"id": "missing", "quantity": 50, "unit_cost": None},
            {"id": "zero-stock", "quantity": 0, "unit_cost": None},
        ])

        result = build_sku_price_completion(rows)

        self.assertEqual(result, {"total": 2, "priced": 1, "missing": 1})

    def test_reference_cost_fill_also_updates_missing_current_inventory(self):
        supabase = _FakeCostSupabase([
            {"id": "missing", "quantity": 100, "unit_cost": 0},
            {"id": "priced", "quantity": 200, "unit_cost": 1.67},
            {"id": "empty", "quantity": 0, "unit_cost": 0},
        ])
        groups = pd.DataFrame([{
            "department": "DTF", "category": "黑白短袖",
            "brand": "Haloo", "material": "180g", "color": "白",
        }])

        updated = fill_missing_inventory_group_costs(
            supabase, groups, 0.9182
        )

        self.assertEqual(updated, 1)
        self.assertEqual(supabase.updated_ids, ["missing"])
        self.assertEqual(supabase.updated_value, 0.9182)

    def test_colored_cost_uses_prior_same_brand_material_and_size(self):
        rows = pd.DataFrame([
            _colored_cost_row(
                "haloo-old", "old", "Haloo", "蓝色", "S", 100, 1.6,
                "2026-08-01",
            ),
            _colored_cost_row(
                "temp-old", "old-temp", "临时进货", "绿色", "S", 100,
                2.06, "2026-08-02",
            ),
            _colored_cost_row(
                "haloo-missing", "new", "Haloo", "粉色", "S", 200,
                None, "2026-08-10",
            ),
            _colored_cost_row(
                "temp-missing", "new-temp", "临时进货", "紫色", "S", 300,
                None, "2026-08-10",
            ),
        ])

        result = match_previous_brand_costs(rows).set_index("record_id")

        self.assertEqual(result.loc["haloo-missing", "reference_cost"], 1.6)
        self.assertEqual(result.loc["temp-missing", "reference_cost"], 2.06)

    def test_colored_cost_backfills_from_first_later_same_size_price(self):
        rows = pd.DataFrame([
            _colored_cost_row(
                "prior-xl", "old", "Haloo", "蓝色", "XL", 100, 1.6,
                "2026-08-01",
            ),
            _colored_cost_row(
                "future-s", "future", "Haloo", "绿色", "S", 100, 1.8,
                "2026-08-20",
            ),
            _colored_cost_row(
                "missing-s", "new", "Haloo", "粉色", "S", 200, None,
                "2026-08-10",
            ),
        ])

        result = match_previous_brand_costs(rows)

        self.assertEqual(result.iloc[0]["reference_cost"], 1.8)
        self.assertEqual(result.iloc[0]["reference_mode"], "回溯参考")

    def test_colored_previous_cost_preview_is_wide(self):
        rows = pd.DataFrame([
            _colored_cost_row(
                "old-s", "old", "Haloo", "蓝色", "S", 100, 1.6,
                "2026-08-01",
            ),
            _colored_cost_row(
                "new-s", "new", "Haloo", "粉色", "S", 200, None,
                "2026-08-10",
            ),
        ])

        preview = build_previous_brand_cost_preview(
            match_previous_brand_costs(rows)
        )

        self.assertEqual(preview.iloc[0]["S"], "200 × $1.6000")
        self.assertEqual(preview.iloc[0]["总件数"], 200)

    def test_inventory_navigation_is_grouped(self):
        inventory_section = next(
            items for title, items in NAV_SECTIONS if title == "库存"
        )
        self.assertEqual(
            [label for _, label, _ in inventory_section],
            [
                "库存总结", "生产库存", "耗材库存", "货柜安排",
                "仓库调拨", "客户销售出库", "SKU 管理",
            ],
        )
        independent = [
            label
            for title, items in NAV_SECTIONS
            if title is None
            for _, label, _ in items
        ]
        self.assertIn("财务", independent)
        self.assertIn("手机壳图片处理", independent)


def _finance_inbound(record_id, batch_id, size, quantity, cost, recorded_at):
    return {
        "record_id": record_id, "batch_id": batch_id,
        "recorded_at": recorded_at, "date": "2026-08-06",
        "direction": "入库", "department": "UV", "category": "铁板画",
        "brand": "", "material": "铝牌", "color": "白", "size": size,
        "quantity": quantity, "unit_cost": cost,
        "amount": quantity * cost, "source_type": "transfer",
        "missing_cost": False,
    }


def _dtf_cost_row(
    record_id, batch_id, brand, material, color, size,
    quantity, cost, business_date,
):
    return {
        "record_id": record_id, "batch_id": batch_id,
        "business_batch_label": f"测试批次 {batch_id}",
        "recorded_at": f"{business_date}T12:00:00Z",
        "date": business_date, "direction": "入库",
        "department": "DTF", "category": "黑白短袖",
        "brand": brand, "material": material, "color": color,
        "size": size, "quantity": quantity, "unit_cost": cost,
        "amount": 0 if not cost else quantity * cost,
        "source_type": "bulk", "missing_cost": not cost,
    }


def _colored_cost_row(
    record_id, batch_id, brand, color, size, quantity, cost, business_date,
):
    return {
        **_dtf_cost_row(
            record_id, batch_id, brand, "180g", color, size,
            quantity, cost, business_date,
        ),
        "category": "彩色短袖",
    }


class _FakeCostResponse:
    def __init__(self, data):
        self.data = data


class _FakeCostQuery:
    def __init__(self, owner, mode):
        self.owner = owner
        self.mode = mode
        self.ids = []

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def gt(self, column, value):
        if column == "quantity":
            self.owner.rows = [
                row for row in self.owner.rows
                if float(row.get("quantity") or 0) > value
            ]
        return self

    def update(self, values):
        self.mode = "update"
        self.owner.updated_value = values["unit_cost"]
        return self

    def in_(self, _column, ids):
        self.ids = list(ids)
        return self

    def execute(self):
        if self.mode == "update":
            self.owner.updated_ids.extend(self.ids)
            return _FakeCostResponse([{"id": value} for value in self.ids])
        return _FakeCostResponse(list(self.owner.rows))


class _FakeCostSupabase:
    def __init__(self, rows):
        self.rows = list(rows)
        self.updated_ids = []
        self.updated_value = None

    def table(self, _name):
        return _FakeCostQuery(self, "select")


if __name__ == "__main__":
    unittest.main()
