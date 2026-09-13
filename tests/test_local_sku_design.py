import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from db.inventory.master_data.local_design import (
    read_local_design, write_local_design, validate_model, model_paths,
)
from db.inventory.master_data.hierarchy import save_hierarchy_definition
from streamlit.testing.v1 import AppTest


class LocalSkuDesignTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "models.json"
        self.runtime = patch("db.inventory.master_data.local_design.is_deployed_runtime", return_value=False)
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def write(self, action, model_id, payload):
        return write_local_design(action, model_id, payload, read_local_design(self.path)["version"], "Andy", self.path)

    def test_deep_model_options_sku_rename_and_persistent_audit(self):
        nodes = [dict(id=f"n{i}",parent=f"n{i-1}" if i else "",label=f"自定义层{i}") for i in range(9)]
        model_id = self.write("create_model", "", dict(name="试验设备",nodes=nodes))
        parent = ""
        path = []
        for node in nodes:
            self.write("add_option", model_id, dict(node=node["id"],parent=parent,value="选项"))
            parent = read_local_design(self.path)["models"][model_id]["values"][-1]["id"]
            path.append(parent)
        self.write("add_sku", model_id, dict(name="设备A",path=path))
        data = read_local_design(self.path)
        sku_id = data["models"][model_id]["skus"][0]["id"]
        nodes[0]["label"] = "产品线"
        self.write("save_structure", model_id, dict(nodes=nodes))
        data = read_local_design(self.path)
        self.assertEqual(data["models"][model_id]["skus"][0]["id"], sku_id)
        rows, paths = model_paths(data["models"][model_id])
        self.assertEqual(len(paths[0]), 9)
        self.assertEqual(rows[0]["n8"], "选项")
        self.assertEqual(data["history"][-1]["operator"], "Andy")
        self.assertTrue(data["history"][-1]["at"].endswith("+00:00"))
        self.assertEqual(data["history"][-1]["before"]["nodes"][0]["label"], "自定义层0")

    def test_variable_depth_cycle_and_invalid_parent_validation(self):
        model = dict(nodes=[dict(id="root",parent="",label="部门"),dict(id="a",parent="root",label="品类"),
                           dict(id="b",parent="a",label="配置"),dict(id="c",parent="root",label="服务")],values=[],skus=[])
        validate_model(model)
        _, paths = model_paths(model)
        self.assertEqual(sorted(map(len,paths)), [2,3])
        broken = copy.deepcopy(model)
        broken["nodes"][0]["parent"] = "b"
        with self.assertRaises(ValueError):
            validate_model(broken)
        broken = copy.deepcopy(model)
        broken["values"] = [dict(id="v",node="a",parent="",value="不能跨父层")]
        with self.assertRaises(ValueError):
            validate_model(broken)

    def test_deployed_write_and_legacy_write_are_rejected(self):
        with patch("db.inventory.master_data.local_design.is_deployed_runtime", return_value=True):
            with self.assertRaises(PermissionError):
                write_local_design("create_model", "", {}, 0, "Andy", self.path)
            client = Mock()
            with self.assertRaises(PermissionError):
                save_hierarchy_definition(client,"DTF","短袖",[],0,"Andy")
            client.rpc.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_optimistic_version_duplicate_options_and_system_actor(self):
        model_id = self.write("create_model", "", dict(name="模型",nodes=[dict(id="r",parent="",label="第一层")]))
        self.write("add_option",model_id,dict(node="r",parent="",value="A"))
        with self.assertRaises(ValueError):
            self.write("add_option",model_id,dict(node="r",parent="",value="A"))
        with self.assertRaises(ValueError):
            write_local_design("save_structure",model_id,{},0,"Andy",self.path)
        with self.assertRaises(ValueError):
            write_local_design("create_model","",{},2,"system",self.path)
        self.assertEqual(read_local_design(self.path)["version"],2)

    def test_deployment_hides_designer_even_for_manager(self):
        app = AppTest.from_string('''
from unittest.mock import patch
import ui.inventory.sku.page as page
with patch.object(page,"is_deployed_runtime",return_value=True), patch.object(page,"load_master_data",side_effect=RuntimeError("fixture stop")):
    page.render_sku_management(None,"UV",True)
''').run()
        self.assertFalse(app.exception)
        self.assertFalse(any(widget.label == "SKU 工作模式" for widget in app.get("segmented_control")))

    def test_browser_form_save_does_not_mutate_instantiated_model_widget(self):
        source = f'''
from pathlib import Path
import db.inventory.master_data.local_design as store
import ui.inventory.sku.model_designer as designer
store.STORE_PATH = Path({str(self.path)!r})
designer.get_current_operator_name = lambda: "Andy"
designer.render_local_model_designer()
'''
        app = AppTest.from_string(source).run()
        app.text_input[0].set_value("设备模型")
        app.text_input[1].set_value("产品线")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        next(widget for widget in app.text_input if widget.label == "新增 产品线 选项").set_value("设备")
        next(button for button in app.button if button.label == "保存本地选项").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        model = next(iter(read_local_design(self.path)["models"].values()))
        self.assertEqual([value["value"] for value in model["values"]], ["设备"])


if __name__ == "__main__":
    unittest.main()
