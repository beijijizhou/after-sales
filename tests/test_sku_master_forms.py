import unittest
from unittest.mock import patch

import pandas as pd

from ui.inventory.sku.master_forms import _save
from ui.inventory.sku.create import (
    build_black_white_sku_rows,
    materials_for_category,
)


class SkuMasterFormTests(unittest.TestCase):
    def test_black_white_category_generates_fixed_colors_and_sizes(self):
        result = build_black_white_sku_rows("Caribbean", "180g")

        self.assertEqual(len(result), 16)
        self.assertEqual(set(result["颜色"]), {"黑", "白"})
        self.assertEqual(
            result.groupby("颜色")["规格"].apply(list).to_dict(),
            {
                "白": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
                "黑": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
            },
        )
        self.assertEqual(set(result["品牌"]), {"Caribbean"})
        self.assertEqual(set(result["材质"]), {"180g"})

    def test_new_sku_only_lists_materials_for_selected_category(self):
        materials = pd.DataFrame([
            {
                "id": "material-1", "name": "160g", "is_active": True,
                "category_id": "tshirt",
            },
            {
                "id": "material-2", "name": "铝", "is_active": True,
                "category_id": "plate",
            },
            {
                "id": "material-3", "name": "180g", "is_active": False,
                "category_id": "tshirt",
            },
        ])

        result = materials_for_category(materials, "tshirt")

        self.assertEqual(result["name"].tolist(), ["160g"])

    @patch("ui.inventory.sku.master_forms.st.rerun")
    @patch("ui.inventory.sku.master_forms.st.session_state", {})
    def test_saving_master_data_refreshes_sku_editor(self, rerun):
        _save(lambda: None, "品牌已新增")

        from ui.inventory.sku import master_forms

        self.assertEqual(
            master_forms.st.session_state["sku_master_editor_version"], 1
        )
        rerun.assert_called_once()


if __name__ == "__main__":
    unittest.main()
