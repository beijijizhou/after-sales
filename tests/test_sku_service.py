import unittest
from unittest.mock import Mock

import pandas as pd

from db.inventory.master_data.sku_service import (
    build_sku_merge_preview,
    update_skus,
)


class _Response:
    data = []


class _UpdateQuery:
    def __init__(self, rows=None):
        self.values = None
        self.rows = rows or []

    def select(self, *_args):
        return self

    def update(self, values):
        self.values = values
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        response = _Response()
        response.data = self.rows
        return response


class SkuServiceTests(unittest.TestCase):
    def test_update_generates_consistent_name_when_original_is_blank(self):
        query = _UpdateQuery([{"id": "sku-1", "size": "L"}])
        supabase = Mock()
        supabase.table.return_value = query
        supabase.rpc.return_value.execute.return_value = _Response()
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
        materials = pd.DataFrame([{
            "id": "material-1", "name": "160g", "is_active": True,
        }])

        updated = update_skus(
            supabase, original, edited, categories, brands, materials
        )

        self.assertEqual(updated, 1)
        self.assertEqual(
            query.values["sku_name"],
            "黑白短袖 Caribbean 160g 白 L",
        )
        self.assertEqual(
            supabase.rpc.call_args.args[0],
            "update_inventory_sku_identities",
        )

    def test_existing_brand_is_merged_instead_of_rejected_as_duplicate(self):
        query = _UpdateQuery([
            {"id": "target-s", "size": "S"},
            {"id": "target-l", "size": "L"},
        ])
        supabase = Mock()
        supabase.table.return_value = query
        supabase.rpc.return_value.execute.return_value = _Response()
        original = pd.DataFrame([
            _sku("source-s", "Cotton", "S"),
            _sku("source-l", "Cotton", "L"),
            _sku("target-s", "Caribbean", "S"),
            _sku("target-l", "Caribbean", "L"),
        ])
        edited = original.copy()
        edited.loc[edited["brand"] == "Cotton", "brand"] = "Caribbean"
        categories = pd.DataFrame([{
            "id": "cat-1", "name": "黑白短袖",
            "specification_type": "size",
        }])
        brands = pd.DataFrame([{
            "id": "brand-1", "name": "Caribbean", "is_active": True,
        }])
        materials = pd.DataFrame([{
            "id": "material-1", "name": "160g", "is_active": True,
        }])

        updated = update_skus(
            supabase, original, edited, categories, brands, materials,
            department_code="DTF", changed_by="Andy",
        )

        self.assertEqual(updated, 2)
        parameters = supabase.rpc.call_args.args[1]
        self.assertEqual(parameters["p_changed_by"], "Andy")
        self.assertEqual(parameters["p_changes"], [{
            "old_category": "黑白短袖", "old_brand": "Cotton",
            "old_material": "160g", "old_color": "白",
            "new_category": "黑白短袖", "new_brand": "Caribbean",
            "new_material": "160g", "new_color": "白",
        }])
        self.assertEqual(build_sku_merge_preview(original, edited), [{
            "old_brand": "Cotton", "new_brand": "Caribbean",
            "sku_count": 2, "overlap_count": 2, "quantity": 0,
        }])

    def test_brand_change_from_one_filtered_size_applies_to_whole_size_group(self):
        query = _UpdateQuery([
            {"id": "target-s", "size": "S"},
            {"id": "target-l", "size": "L"},
        ])
        supabase = Mock()
        supabase.table.return_value = query
        supabase.rpc.return_value.execute.return_value = _Response()
        original = pd.DataFrame([
            _sku("source-s", "Cotton", "S"),
            _sku("source-l", "Cotton", "L"),
            _sku("target-s", "Caribbean", "S"),
            _sku("target-l", "Caribbean", "L"),
        ])
        edited = original.copy()
        edited.loc[edited["id"] == "source-l", "brand"] = "Caribbean"
        categories = pd.DataFrame([{
            "id": "cat-1", "name": "黑白短袖",
            "specification_type": "size",
        }])
        brands = pd.DataFrame([{
            "id": "brand-1", "name": "Caribbean", "is_active": True,
        }])
        materials = pd.DataFrame([{
            "id": "material-1", "name": "160g", "is_active": True,
        }])

        updated = update_skus(
            supabase, original, edited, categories, brands, materials,
            department_code="DTF", changed_by="Andy",
        )

        self.assertEqual(updated, 2)
        change = supabase.rpc.call_args.args[1]["p_changes"][0]
        self.assertEqual(change["old_brand"], "Cotton")
        self.assertEqual(change["new_brand"], "Caribbean")

    def test_update_rejects_material_outside_fixed_options(self):
        original = pd.DataFrame([{
            "id": "sku-1", "sku_name": "黑白短袖 160g 白 L",
            "category": "黑白短袖", "brand": "",
            "material": "160g", "color": "白", "规格": "L",
            "unit": "件", "is_active": True,
        }])
        edited = original.copy()
        edited.loc[0, "material"] = "160克"
        categories = pd.DataFrame([{
            "id": "cat-1", "name": "黑白短袖",
            "specification_type": "size",
        }])
        materials = pd.DataFrame([{
            "id": "material-1", "name": "160g", "is_active": True,
        }])

        with self.assertRaisesRegex(ValueError, "请选择有效材质"):
            update_skus(
                Mock(), original, edited, categories,
                pd.DataFrame(columns=["id", "name"]), materials,
            )


def _sku(item_id, brand, size):
    return {
        "id": item_id, "sku_name": "", "department": "DTF",
        "category": "黑白短袖", "brand": brand, "material": "160g",
        "color": "白", "规格": size, "unit": "件", "quantity": 0,
        "is_active": True,
    }


if __name__ == "__main__":
    unittest.main()
