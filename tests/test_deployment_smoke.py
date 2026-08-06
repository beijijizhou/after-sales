from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from automation.deployment.streamlit_smoke import (
    build_page_urls,
    page_error_message,
)


class DeploymentSmokeTests(unittest.TestCase):
    def test_builds_main_and_encoded_page_urls(self):
        with TemporaryDirectory() as directory:
            pages = Path(directory)
            (pages / "4_库存.py").touch()
            (pages / "11_物流追踪.py").touch()

            urls = build_page_urls("https://example.streamlit.app/", pages)

        self.assertEqual(urls, [
            ("主页", "https://example.streamlit.app/"),
            (
                "物流追踪",
                "https://example.streamlit.app/"
                "%E7%89%A9%E6%B5%81%E8%BF%BD%E8%B8%AA",
            ),
            (
                "库存",
                "https://example.streamlit.app/"
                "%E5%BA%93%E5%AD%98",
            ),
        ])

    def test_detects_streamlit_redacted_import_error(self):
        message = page_error_message(
            "This app has encountered an error. ImportError"
        )
        self.assertEqual(message, "this app has encountered an error")

    def test_detects_streamlit_exception_component(self):
        message = page_error_message("登录", ["ModuleNotFoundError: demo"])
        self.assertEqual(message, "ModuleNotFoundError: demo")

    def test_login_page_is_not_an_application_error(self):
        self.assertEqual(page_error_message("登录 请输入账号"), "")


if __name__ == "__main__":
    unittest.main()
