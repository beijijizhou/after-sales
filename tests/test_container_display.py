import unittest
from datetime import date

import pandas as pd

from db.inventory.container.tables import (
    build_arrival_batch_summary,
    build_container_display,
    build_container_template,
    build_filtered_container_summary,
    build_container_inventory_summary,
    normalize_container_rows,
    sort_arrival_history_rows,
)
from ui.inventory.container.tables import calculate_container_totals


def container_row(department, material, item, quantity):
    return {
        "container_key": "9柜",
        "shipped_date": date(2026, 6, 5),
        "expected_arrival_date": date(2026, 7, 20),
        "actual_arrival_date": date(2026, 7, 28),
        "actual_arrival_at": "2026-07-28T15:30:00-04:00",
        "container_no": "9柜",
        "department": department,
        "category": "铁板画" if department == "UV" else "黑白短袖",
        "brand": "",
        "material": material,
        "color": "白",
        "size": item,
        "quantity": quantity,
        "status": "已到货",
        "note": "",
    }


class ContainerDisplayTests(unittest.TestCase):
    def test_arrival_history_collapses_sku_rows_into_container_batches(self):
        rows = pd.DataFrame([
            {
                "container_key": "第十四柜", "container_no": "TRHU5477320",
                "department": "UV", "category": "铁板画", "brand": "",
                "material": "铁牌", "color": "白", "size": "2030",
                "quantity": 55000, "status": "已入库",
                "actual_arrival_date": "2026-08-17",
                "arrival_confirmed_at": "2026-08-17T15:00:00Z",
                "note": "第十四柜",
            },
            {
                "container_key": "第十四柜", "container_no": "TRHU5477320",
                "department": "UV", "category": "铁板画", "brand": "",
                "material": "铁牌", "color": "白", "size": "1040",
                "quantity": 10000, "status": "已入库",
                "actual_arrival_date": "2026-08-17",
                "arrival_confirmed_at": "2026-08-17T15:00:00Z",
                "note": "第十四柜",
            },
        ])

        result = build_arrival_batch_summary(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result.loc[0, "货柜批次"], "第十四柜｜柜号 TRHU5477320"
        )
        self.assertEqual(result.loc[0, "SKU数"], 2)
        self.assertEqual(result.loc[0, "总件数"], 65000)
        self.assertEqual(
            result.loc[0, "实际到柜日期"].isoformat(), "2026-08-17"
        )

    def test_arrival_history_can_sort_by_latest_time(self):
        rows = pd.DataFrame([
            {
                "container_no": "DTF-OLD", "department": "DTF",
                "actual_arrival_date": "2026-08-01",
                "actual_arrival_at": "2026-08-01T09:00:00-04:00",
            },
            {
                "container_no": "UV-NEW", "department": "UV",
                "actual_arrival_date": "2026-08-05",
                "actual_arrival_at": "2026-08-05T10:00:00-04:00",
            },
        ])

        result = sort_arrival_history_rows(rows, mode="time")

        self.assertEqual(
            result["container_no"].tolist(), ["UV-NEW", "DTF-OLD"]
        )

    def test_arrival_history_prioritizes_confirmation_time(self):
        rows = pd.DataFrame([
            {
                "container_no": "CONFIRMED-LATEST",
                "department": "DTF",
                "actual_arrival_date": "2026-08-01",
                "actual_arrival_at": "2026-08-01T09:00:00-04:00",
                "arrival_confirmed_at": "2026-08-06T15:00:00+00:00",
            },
            {
                "container_no": "ARRIVED-LATEST",
                "department": "UV",
                "actual_arrival_date": "2026-08-05",
                "actual_arrival_at": "2026-08-05T10:00:00-04:00",
                "arrival_confirmed_at": "2026-08-05T15:00:00+00:00",
            },
        ])

        result = sort_arrival_history_rows(rows, mode="time")

        self.assertEqual(result["container_no"].tolist(), [
            "CONFIRMED-LATEST", "ARRIVED-LATEST",
        ])

    def test_arrival_history_can_sort_by_department_then_latest_time(self):
        rows = pd.DataFrame([
            {
                "container_no": "UV", "department": "UV",
                "actual_arrival_date": "2026-08-05",
            },
            {
                "container_no": "DTF-OLD", "department": "DTF",
                "actual_arrival_date": "2026-08-01",
            },
            {
                "container_no": "DTF-NEW", "department": "DTF",
                "actual_arrival_date": "2026-08-04",
            },
        ])

        result = sort_arrival_history_rows(rows, mode="department")

        self.assertEqual(
            result["container_no"].tolist(),
            ["DTF-NEW", "DTF-OLD", "UV"],
        )

    def test_new_container_defaults_to_55_transit_days(self):
        template = build_container_template(today=date(2026, 7, 30))

        self.assertEqual(template.iloc[0]["预计运输天数"], 55)

    def test_business_batch_key_groups_rows_without_physical_container_no(self):
        source = pd.DataFrame([
            {
                "货柜记录ID": "363m紫色T｜08/13到货",
                "发货日期": date(2026, 6, 19), "预计运输天数": 55,
                "货柜号": "", "部门": "DTF", "品类": "彩色短袖",
                "品牌": "Haloo", "材质": "180g", "颜色": "紫色",
                "型号": size, "数量": 216, "成本": 2.44,
                "状态": "在途", "备注": "363m",
            }
            for size in ["L", "XL"]
        ])

        result = normalize_container_rows(source)

        self.assertEqual(result["货柜记录ID"].nunique(), 1)
        self.assertEqual(result["货柜记录ID"].iloc[0], "363m紫色T｜08/13到货")
        self.assertTrue(result["货柜号"].eq("").all())

    def test_non_apparel_container_item_can_use_blank_color(self):
        source = pd.DataFrame([{
            "货柜记录ID": "第十四柜",
            "发货日期": date(2026, 7, 8), "预计运输天数": 48,
            "货柜号": "TRHU5477320", "部门": "UV", "品类": "保温杯",
            "品牌": "", "材质": "直杯", "颜色": "",
            "型号": "600ML", "数量": 8700, "成本": 2.362,
            "状态": "在途", "备注": "B20｜174箱×50件",
        }])

        result = normalize_container_rows(source)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["颜色"], "")

    def test_apparel_container_item_still_requires_color(self):
        source = pd.DataFrame([{
            "货柜记录ID": "T-60",
            "发货日期": date(2026, 8, 25), "预计运输天数": 1,
            "货柜号": "", "部门": "DTF", "品类": "黑白短袖",
            "品牌": "杂牌", "材质": "160g", "颜色": "",
            "型号": "M", "数量": 1440, "成本": 1.38,
            "状态": "在途", "备注": "颜色缺失",
        }])

        result = normalize_container_rows(source)

        self.assertTrue(result.empty)

    def test_uv_uses_compact_model_rows(self):
        source = pd.DataFrame([
            container_row("UV", "铁牌", "1040", 20_000),
            container_row("UV", "铝牌", "YUAN", 20_100),
        ])

        display = build_container_display(source)

        self.assertEqual(display["型号"].tolist(), ["1040", "YUAN"])
        self.assertEqual(display["数量"].tolist(), [20_000, 20_100])
        self.assertEqual(
            display.loc[0, "实际到货时间（纽约）"],
            "2026-07-28 15:30:00",
        )
        self.assertNotIn("S", display.columns)
        self.assertNotIn("5XL", display.columns)

    def test_display_uses_business_remark_before_physical_number(self):
        source = pd.DataFrame([{
            **container_row("UV", "铁牌", "2030", 65_000),
            "container_key": "12柜",
            "container_no": "ZCSU7707166",
            "note": "货柜汇总核对：表格第十柜；明细一致",
        }])

        display = build_container_display(source)

        self.assertEqual(
            display.iloc[0]["批次标识"],
            "第十柜｜柜号 ZCSU7707166",
        )
        self.assertEqual(display.iloc[0]["货柜号"], "ZCSU7707166")

    def test_dtf_keeps_size_columns(self):
        source = pd.DataFrame([
            container_row("DTF", "180g", "S", 72),
        ])

        display = build_container_display(source)

        self.assertEqual(display.loc[0, "S"], 72)
        self.assertNotIn("型号", display.columns)

    def test_container_totals_include_every_cost_group(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "160g", "L", 19_008),
                "unit_cost": 1.38,
            },
            {
                **container_row("DTF", "160g", "4XL", 3_500),
                "unit_cost": 1.88,
            },
        ])
        display = build_container_display(source, include_cost=True)

        quantity, cost = calculate_container_totals(display)

        self.assertEqual(quantity, 22_508)
        self.assertAlmostEqual(cost, 32_811.04)

    def test_dtf_summary_combines_brands_and_materials(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "180g", "S", 72),
                "brand": "Haloo",
                "color": "黑",
            },
            {
                **container_row("DTF", "CVC", "S", 100),
                "brand": "临时进货",
                "color": "黑",
            },
        ])

        summary = build_container_inventory_summary(
            build_container_display(source)
        )

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["S"], 172)
        self.assertEqual(summary.iloc[0]["总件数"], 172)

    def test_uv_summary_uses_models_instead_of_sizes(self):
        source = pd.DataFrame([
            container_row("UV", "铁牌", "1040", 20_000),
            container_row("UV", "铁牌", "2030", 40_000),
        ])

        summary = build_container_inventory_summary(
            build_container_display(source)
        )

        self.assertEqual(summary.iloc[0]["1040"], 20_000)
        self.assertEqual(summary.iloc[0]["2030"], 40_000)
        self.assertEqual(summary.iloc[0]["总件数"], 60_000)
        self.assertNotIn("S", summary.columns)

    def test_filtered_summary_keeps_business_dimensions(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "180g", "S", 72),
                "brand": "Haloo",
                "color": "黑",
            },
            {
                **container_row("DTF", "CVC", "S", 100),
                "brand": "临时进货",
                "color": "黑",
                "container_key": "10柜",
                "container_no": "10柜",
            },
        ])

        summary = build_filtered_container_summary(source)

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary["总件数"].sum(), 172)
        self.assertEqual(set(summary["品牌"]), {"Haloo", "临时进货"})
        self.assertEqual(set(summary["涉及货柜"]), {"9柜", "10柜"})

    def test_filtered_summary_shows_same_container_for_color_rows(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "160g", "L", 19_008),
                "brand": "加州",
                "color": "白",
            },
            {
                **container_row("DTF", "160g", "3XL", 5_460),
                "brand": "加州",
                "color": "黑",
            },
        ])

        summary = build_filtered_container_summary(source)

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary["涉及货柜"].tolist(), ["9柜", "9柜"])

    def test_filtered_summary_combines_containers_and_lists_them(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "160g", "L", 100),
                "brand": "加州",
            },
            {
                **container_row("DTF", "160g", "L", 200),
                "brand": "加州",
                "container_key": "10柜",
                "container_no": "10柜",
            },
        ])

        summary = build_filtered_container_summary(source)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["涉及货柜"], "9柜、10柜")
        self.assertEqual(summary.iloc[0]["L"], 300)


if __name__ == "__main__":
    unittest.main()
