import unittest
from unittest.mock import patch

from ui.inventory.sku.master_forms import _save


class SkuMasterFormTests(unittest.TestCase):
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
