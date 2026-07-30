import unittest

from db.inventory.master_data.phone_cases import (
    build_phone_case_sku_rows,
)
from utils.image_tools.templates import (
    get_dieline_materials,
    get_dieline_models,
)


class PhoneCaseSkuTests(unittest.TestCase):
    def test_sku_rows_match_image_processing_catalog(self):
        rows = build_phone_case_sku_rows()
        expected = {
            (material, model)
            for material in get_dieline_materials()
            for model in get_dieline_models(material)
        }
        actual = {
            (row["材质"], row["规格"])
            for row in rows
        }

        self.assertEqual(actual, expected)
        self.assertEqual(len(rows), len(expected))


if __name__ == "__main__":
    unittest.main()
