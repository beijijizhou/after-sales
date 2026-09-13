import unittest

from streamlit.testing.v1 import AppTest


APP = '''
from datetime import date
import streamlit as st
from ui.inventory.operations.outbound_entry import render_sku_outbound_entry, SKU_ENTRY_TEXT
lookup = {}
for category in ['彩色短袖', '黑白短袖']:
    for material in ['180g', 'CVC']:
        for brand in ['Haloo', "Men's"]:
            for color in ['白', '黑']:
                for size in ['L', 'M', 'S', 'XL']:
                    label = '/'.join([category, material, brand, color, size])
                    lookup[label] = dict(category=category, material=material, brand=brand, color=color, size=size)
adjustments, preview = render_sku_outbound_entry(
    lookup, date(2026, 9, 12), {}, {}, SKU_ENTRY_TEXT['zh'], 'zh', 0, 'test', scope='DTF')
st.session_state['qa_preview'] = preview.to_dict('records')
'''


class OutboundHierarchyTests(unittest.TestCase):
    def test_table_only_entry_has_no_second_filter_set(self):
        app = AppTest.from_string(APP.replace("scope='DTF'", "scope='DTF', show_scope_selectors=False")).run()
        self.assertFalse(app.exception)
        self.assertEqual([widget.label for widget in app.selectbox],
                         ['品类', '材质', '品牌', '颜色', '尺码', '包装单位'])
        self.assertEqual(len(app.multiselect), 0)

    def test_table_dimension_selection_and_quantity_survive_first_edit(self):
        app = AppTest.from_string(APP.replace("scope='DTF'", "scope='DTF', show_scope_selectors=False")).run()
        app.selectbox[1].set_value('CVC').run()
        app.selectbox[4].set_value('M').run()
        app.number_input[1].set_value(12).run()
        app.run()
        preview = app.session_state['qa_preview']
        self.assertEqual(preview[0]['材质'], 'CVC')
        self.assertEqual(preview[0]['尺码'], 'M')
        self.assertEqual(preview[0]['总件数'], 12)
        self.assertFalse(app.exception)

    def test_each_row_material_limits_its_brand_and_resets_quantity(self):
        restricted = APP.replace("['180g', 'CVC']", "['180g', '160g']").replace(
            "['Haloo', \"Men's\"]", "['Haloo', 'SK', '杂牌']").replace(
            "                    label =", "                    if (material == '180g' and brand == '杂牌') or (material == '160g' and brand != '杂牌'):\n                        continue\n                    label =")
        app = AppTest.from_string(restricted.replace("scope='DTF'", "scope='DTF', show_scope_selectors=False")).run()
        app.selectbox[1].set_value('180g').run()
        self.assertEqual(app.selectbox[2].options, ['Haloo', 'SK'])
        app.selectbox[2].set_value('SK').run()
        app.number_input[1].set_value(10).run()
        next(button for button in app.button if button.label == '+ 添加出库行').click().run()
        self.assertEqual(app.selectbox[8].options, ['杂牌'])
        app.selectbox[1].set_value('160g').run()
        self.assertEqual(app.selectbox[2].options, ['杂牌'])
        self.assertEqual(app.number_input[1].value, 0)
        self.assertFalse(app.exception)

    def test_uv_reuses_hierarchy_without_brand_or_color_controls(self):
        app = AppTest.from_string(APP.replace("scope='DTF'", "scope='UV', compact_sku=True")).run()
        self.assertFalse(app.exception)
        self.assertEqual([widget.label for widget in app.selectbox],
                         ['1. 先选品类', '2. 材质'])
        self.assertEqual(len(app.multiselect), 1)

    def test_parent_first_selection_and_single_interaction(self):
        app = AppTest.from_string(APP).run()
        self.assertFalse(app.exception)
        self.assertEqual([widget.label for widget in app.selectbox],
                         ['1. 先选品类', '2. 材质', '3. 品牌', '4. 颜色'])
        app.selectbox[1].set_value('CVC').run()
        self.assertEqual(app.selectbox[1].value, 'CVC')
        app.selectbox[2].set_value("Men's").run()
        self.assertEqual(app.selectbox[2].value, "Men's")
        options = app.multiselect[0].options
        self.assertEqual(options, ['S', 'M', 'L', 'XL'])
        app.multiselect[0].set_value(['彩色短袖/CVC/Men\'s/黑/S']).run()
        app.selectbox[0].set_value('黑白短袖').run()
        self.assertEqual(app.multiselect[0].value, [])

    def test_editor_edit_survives_recalculation_and_repeated_reruns(self):
        app = AppTest.from_string(APP).run()
        label = '彩色短袖/180g/Haloo/黑/S'
        app.multiselect[0].set_value([label]).run()
        self.assertFalse(app.exception)
        editor = next(key for key in app.session_state.filtered_state
                      if key.startswith('daily_outbound_sku_editor_'))
        app.session_state[editor] = {
            'edited_rows': {0: {'数量': 7}}, 'added_rows': [], 'deleted_rows': []}
        app.run()
        app.run()
        self.assertEqual(app.session_state['qa_preview'][0]['总件数'], 7)
        app.multiselect[0].set_value([label, '彩色短袖/180g/Haloo/黑/M']).run()
        self.assertEqual(app.session_state['qa_preview'][0]['总件数'], 7)
        app.multiselect[0].set_value([label]).run()
        self.assertEqual(app.session_state['qa_preview'][0]['总件数'], 7)
        self.assertFalse(app.exception)

    def test_category_identity_does_not_overwrite_another_category(self):
        import pandas as pd
        from db.inventory.operations.outbound import build_outbound_sku_lookup
        rows = [dict(category=category, material='CVC', brand='Haloo',
                     color='黑', size='M') for category in ['彩色短袖', '黑白短袖']]
        lookup = build_outbound_sku_lookup(pd.DataFrame(rows), include_category=True)
        self.assertEqual(len(lookup), 2)
        self.assertEqual({sku['category'] for sku in lookup.values()},
                         {'彩色短袖', '黑白短袖'})
