from datetime import date
import unittest

import pandas as pd

from ui.inventory.container.form import (
    add_container_identity,
    build_container_form_rows,
    keep_container_items,
)


class ContainerFormTests(unittest.TestCase):
    def test_unchecked_object_delete_value_keeps_the_row(self):
        items = pd.DataFrame({
            "材质": ["160g"],
            "删除": pd.Series([False], dtype="object"),
        })

        result = keep_container_items(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["材质"], "160g")

    def test_checked_delete_value_removes_only_selected_row(self):
        items = pd.DataFrame({
            "材质": ["160g", "180g"],
            "删除": pd.Series([False, True], dtype="object"),
        })

        result = keep_container_items(items)

        self.assertEqual(result["材质"].tolist(), ["160g"])

    def test_linked_identity_is_added_once_in_material_brand_order(self):
        identity = {
            "品类": "黑白短袖", "材质": "160g",
            "品牌": "Caribbean", "颜色": "白", "型号": "",
        }

        items, added = add_container_identity(
            pd.DataFrame(), identity, "DTF"
        )
        duplicate, added_again = add_container_identity(
            items, identity, "DTF"
        )

        self.assertTrue(added)
        self.assertFalse(added_again)
        self.assertEqual(len(duplicate), 1)
        self.assertLess(
            list(items.columns).index("材质"),
            list(items.columns).index("品牌"),
        )

    def test_batch_header_is_applied_to_every_linked_item(self):
        items = pd.DataFrame([{
            "品类": "黑白短袖", "材质": "160g",
            "品牌": "Caribbean", "颜色": "白",
            "S": 100, "M": 200, "成本": 1.5,
            "备注": "L 码另柜", "删除": False,
        }])

        result = build_container_form_rows(
            items,
            shipped_date=date(2026, 8, 8),
            transit_days=55,
            container_no="TEST-001",
            department="DTF",
            status="在途",
            container_note="第十六柜",
        )

        self.assertEqual(result.iloc[0]["货柜号"], "TEST-001")
        self.assertEqual(result.iloc[0]["预计运输天数"], 55)
        self.assertEqual(result.iloc[0]["备注"], "第十六柜；L 码另柜")
        self.assertNotIn("删除", result.columns)


if __name__ == "__main__":
    unittest.main()
