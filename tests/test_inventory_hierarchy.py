import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from ui.inventory.shared.hierarchy import DimensionHierarchy, inventory_hierarchy
from ui.inventory.shared.hierarchy import hierarchy_tree_dot
from db.inventory.master_data.hierarchy import save_hierarchy_definition, load_hierarchy_definitions
from unittest.mock import Mock


class HierarchyTests(unittest.TestCase):
    def test_full_sizes_and_matching_colors_are_compressed(self):
        from db.inventory import SIZE_COLUMNS
        hierarchy = DimensionHierarchy(("brand","color","size"), ("品牌","颜色","尺码"))
        rows = pd.DataFrame([dict(brand="Haloo",color=color,size=size) for color in ["黑","白"] for size in SIZE_COLUMNS])
        dot = hierarchy_tree_dot(rows, hierarchy, compact=True)
        self.assertIn('label="黑 · 白"', dot)
        self.assertIn('label="S–5XL（全尺码）"', dot)
        self.assertEqual(dot.count(" -> "), 3)
        self.assertIn("16 个 SKU", dot)

    def test_missing_size_keeps_color_branches_separate(self):
        from db.inventory import SIZE_COLUMNS
        hierarchy = DimensionHierarchy(("color","size"), ("颜色","尺码"))
        rows = pd.DataFrame([dict(color=color,size=size) for color in ["黑","白"] for size in SIZE_COLUMNS if not(color == "白" and size == "M")])
        dot = hierarchy_tree_dot(rows, hierarchy, compact=True)
        self.assertNotIn('label="黑 · 白"', dot)
        self.assertEqual(dot.count('label="S–5XL（全尺码）"'), 1)
        self.assertIn("S · L · XL · 2XL · 3XL · 4XL · 5XL", dot)

    def test_compact_tree_combines_sibling_sizes_without_merging_brands(self):
        hierarchy = DimensionHierarchy(("brand","size"), ("品牌","尺码"))
        rows = pd.DataFrame([dict(brand=brand,size=size) for brand in ["Haloo","SK"] for size in ["S","M","L","XL"]])
        dot = hierarchy_tree_dot(rows, hierarchy, compact=True)
        self.assertEqual(dot.count(" -> "), 4)
        self.assertEqual(dot.count('label="S · M · L · XL"'), 2)
        self.assertIn('label="Haloo"', dot)
        self.assertNotIn('label="SKU"', dot)
    def test_arbitrary_depth_and_same_name_in_different_branches(self):
        fields = tuple(f"level{i}" for i in range(8))
        hierarchy = DimensionHierarchy(fields, fields)
        rows = pd.DataFrame([{field: "相同" for field in fields},
                             {field: "其他" if index == 0 else "相同" for index, field in enumerate(fields)}])
        dot = hierarchy_tree_dot(rows, hierarchy)
        self.assertEqual(dot.count(" -> "), 16)
        self.assertIn("level7", dot)

    def test_persist_uses_audited_rpc_with_actor_and_version(self):
        client = Mock()
        save_hierarchy_definition(client, "DTF", "短袖", [{"field":"size","label":"尺码"}], 3, "Andy")
        self.assertEqual(client.rpc.call_args.args[0], "save_inventory_sku_hierarchy")
        self.assertEqual(client.rpc.call_args.args[1]["p_operator"], "Andy")
        self.assertEqual(client.rpc.call_args.args[1]["p_expected_version"], 3)
        with self.assertRaises(ValueError):
            save_hierarchy_definition(client, "DTF", "短袖", [], 3, "system")

    def test_connection_errors_are_not_hidden_as_initial_config(self):
        client = Mock()
        client.table.return_value.select.return_value.execute.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            load_hierarchy_definitions(client)

    def test_category_design_changes_filter_order_and_omits_unused_fields(self):
        app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from ui.inventory.shared.filters import render_inventory_dimension_filters
st.session_state["sku_hierarchy_definitions"] = {("DTF","黑白短袖"):{"levels":[{"field":"color","label":"颜色"},{"field":"material","label":"材质"},{"field":"size","label":"尺码"}]}}
rows = pd.DataFrame([{"department":"DTF","category":"黑白短袖","material":"180g","brand":"Haloo","color":"黑","size":"M"}])
render_inventory_dimension_filters(rows, key="designed")
''').run()
        self.assertFalse(app.exception)
        self.assertEqual([widget.label for widget in app.multiselect], ["筛选颜色","筛选材质","筛选尺码"])

    def test_tree_view_disables_design_without_database_migration(self):
        app = AppTest.from_string('''
import streamlit as st
import pandas as pd
import ui.inventory.sku.hierarchy as view
view.hydrate_hierarchies = lambda _: ({},False)
view.load_sku_catalog = lambda *args: pd.DataFrame([dict(department="DTF",category="短袖",material="180g",brand="Haloo",color="黑",size="M",model=None,is_active=True)])
view.render_sku_hierarchy(None,"DTF","短袖",True)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["等级树","设计历史"])
        self.assertFalse(any(button.label == "保存层级设计" for button in app.button))

    def test_generic_path_has_no_apparel_value_dependency(self):
        hierarchy = DimensionHierarchy(("family", "variant"), ("大类", "小类"))
        rows = pd.DataFrame([
            {"family": "机器", "variant": "A"},
            {"family": "配件", "variant": "B"},
        ])
        self.assertEqual(hierarchy.narrow(rows, {"family": ["配件"]})["variant"].tolist(), ["B"])
        self.assertNotIn("brand", inventory_hierarchy("UV").fields)

    def test_uv_hides_controls_and_clears_old_filters(self):
        app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from ui.inventory.shared.filters import render_inventory_dimension_filters
if "seeded" not in st.session_state:
    st.session_state["qa_department"] = "UV"
    st.session_state["qa_brands"] = ["旧品牌"]
    st.session_state["qa_colors"] = ["白"]
    st.session_state["seeded"] = True
rows = pd.DataFrame([
 {"department":"UV","category":"铁板画","material":"铝牌","brand":"旧品牌","color":"白","size":"2030"},
 {"department":"DTF","category":"黑白短袖","material":"180g","brand":"Haloo","color":"黑","size":"M"}
])
st.session_state["result"] = render_inventory_dimension_filters(rows, key="qa")
''').run()
        self.assertFalse(app.exception)
        self.assertEqual([widget.label for widget in app.multiselect], ["筛选材质", "筛选型号"])
        self.assertEqual(app.session_state["result"][2], [])
        self.assertEqual(app.session_state["result"][4], [])
        self.assertEqual(app.expander[0].label, "操作等级图 · 新人指引")
        app.selectbox[0].set_value("DTF").run()
        self.assertFalse(app.exception)
        self.assertIn("筛选品牌", [widget.label for widget in app.multiselect])


if __name__ == "__main__":
    unittest.main()
