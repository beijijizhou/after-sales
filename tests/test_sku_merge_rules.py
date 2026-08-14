import unittest
from pathlib import Path

import pandas as pd

from db.inventory.master_data.sku_merge import (
    build_sku_group_merge_preview,
    build_sku_merge_groups,
    compatible_merge_targets,
    group_key,
)


class SkuMergeRuleTests(unittest.TestCase):
    def setUp(self):
        self.catalog = pd.DataFrame([
            {
                "id": "mens-m", "category": "黑白短袖", "brand": "Men's",
                "material": "160g", "color": "白", "size": "M",
                "quantity": 7200,
            },
            {
                "id": "mens-2xl", "category": "黑白短袖", "brand": "Men's",
                "material": "160g", "color": "白", "size": "2XL",
                "quantity": 3600,
            },
            {
                "id": "misc-2xl", "category": "黑白短袖", "brand": "杂牌",
                "material": "160g", "color": "白", "size": "2XL",
                "quantity": 500,
            },
            {
                "id": "misc-black", "category": "黑白短袖", "brand": "杂牌",
                "material": "160g", "color": "黑", "size": "M",
                "quantity": 900,
            },
        ])

    def test_only_same_category_material_and_color_can_be_target(self):
        groups = build_sku_merge_groups(self.catalog)
        source = ("黑白短袖", "Men's", "160g", "白")

        self.assertEqual(
            compatible_merge_targets(groups, source),
            [("黑白短袖", "杂牌", "160g", "白")],
        )

    def test_existing_brand_can_be_target_before_target_skus_exist(self):
        groups = build_sku_merge_groups(self.catalog)
        source = ("黑白短袖", "Men's", "CVC", "白")

        self.assertIn(
            ("黑白短袖", "杂牌", "CVC", "白"),
            compatible_merge_targets(
                groups, source, available_brands=["Men's", "杂牌"]
            ),
        )

    def test_preview_shows_source_target_and_final_by_size(self):
        preview = build_sku_group_merge_preview(
            self.catalog,
            ("黑白短袖", "Men's", "160g", "白"),
            ("黑白短袖", "杂牌", "160g", "白"),
        )

        self.assertEqual(preview["尺码"].tolist(), ["M", "2XL"])
        self.assertEqual(preview["来源当前库存"].tolist(), [7200, 3600])
        self.assertEqual(preview["目标当前库存"].tolist(), [0, 500])
        self.assertEqual(preview["并入后库存"].tolist(), [7200, 4100])

    def test_group_summary_preserves_inventory_total(self):
        groups = build_sku_merge_groups(self.catalog)
        source = groups[
            groups.apply(group_key, axis=1).map(
                lambda value: value == ("黑白短袖", "Men's", "160g", "白")
            )
        ].iloc[0]

        self.assertEqual(int(source["SKU数"]), 2)
        self.assertEqual(int(source["当前库存"]), 10800)

    def test_migration_preserves_history_and_installs_future_routing(self):
        sql = (
            Path(__file__).resolve().parents[1]
            / "sql/inventory/operations/sku_merge_rules.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists public.inventory_sku_merge_rules", sql)
        self.assertIn("create or replace function public.merge_inventory_sku_group", sql)
        self.assertIn("create trigger inventory_container_merge_redirect", sql)
        self.assertNotIn("update public.inventory_movements", sql)


if __name__ == "__main__":
    unittest.main()
