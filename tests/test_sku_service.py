import unittest
from unittest.mock import Mock

import pandas as pd

from db.inventory.master_data.sku_service import update_skus


class _Response:
    data = []


class _UpdateQuery:
    def __init__(self):
        self.values = None

    def update(self, values):
        self.values = values
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        return _Response()


class SkuServiceTests(unittest.TestCase):
    def test_update_generates_consistent_name_when_original_is_blank(self):
        query = _UpdateQuery()
        supabase = Mock()
        supabase.table.return_value = query
        original = pd.DataFrame([{
            "id": "sku-1", "sku_name": "", "category": "黑白短袖",
            "brand": "加州", "material": "160g", "color": "白",
            "规格": "L", "unit": "件", "is_active": True,
        }])
        edited = original.copy()
        edited.loc[0, "brand"] = "Caribbean"
        categories = pd.DataFrame([{
            "id": "cat-1", "name": "黑白短袖",
            "specification_type": "size",
        }])
        brands = pd.DataFrame([{
            "id": "brand-1", "name": "Caribbean", "is_active": True,
        }])

        updated = update_skus(
            supabase, original, edited, categories, brands
        )

        self.assertEqual(updated, 1)
        self.assertEqual(
            query.values["sku_name"],
            "黑白短袖 Caribbean 160g 白 L",
        )


if __name__ == "__main__":
    unittest.main()
