import unittest

from utils.runtime import is_deployed_runtime


class RuntimeTests(unittest.TestCase):
    def test_streamlit_cloud_is_deployed(self):
        self.assertTrue(is_deployed_runtime(
            {"STREAMLIT_SHARING_MODE": "true"}, "/workspace/app.py",
        ))

    def test_production_environment_is_deployed(self):
        self.assertTrue(is_deployed_runtime(
            {"APP_ENV": "production"}, "/workspace/app.py",
        ))

    def test_mount_source_is_deployed(self):
        self.assertTrue(is_deployed_runtime({}, "/mount/src/after-sales/app.py"))

    def test_local_workspace_is_development(self):
        self.assertFalse(is_deployed_runtime({}, "/Users/example/project/app.py"))


if __name__ == "__main__":
    unittest.main()
