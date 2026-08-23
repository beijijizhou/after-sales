from pathlib import Path
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import utils.auth
from utils.page_layout import BRAND_ORANGE, BRAND_TEAL, BRAND_YELLOW


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_FILES = [PROJECT_ROOT / "app.py", *sorted(
    (PROJECT_ROOT / "pages").glob("*.py")
)]


class PageSmokeTests(unittest.TestCase):
    def test_global_brand_theme_uses_logo_palette(self):
        layout_source = (
            PROJECT_ROOT / "utils" / "page_layout.py"
        ).read_text(encoding="utf-8")
        auth_source = (
            PROJECT_ROOT / "utils" / "auth" / "ui.py"
        ).read_text(encoding="utf-8")

        self.assertTrue(
            (PROJECT_ROOT / "assets" / "brand" / "production-logo.jpg").exists()
        )
        self.assertIn(BRAND_ORANGE, layout_source)
        self.assertIn(BRAND_TEAL, layout_source)
        self.assertIn(BRAND_YELLOW, layout_source)
        self.assertIn('[data-testid="stAppViewContainer"]', layout_source)
        self.assertIn("background-size: 28px 28px", layout_source)
        self.assertIn("render_brand_header()", auth_source)

    def test_every_streamlit_page_loads_without_import_error(self):
        def stop_before_business_queries(_page_key=None):
            st.stop()

        patches = (
            patch.object(
                utils.auth,
                "require_page_access",
                stop_before_business_queries,
            ),
            patch.object(utils.auth, "render_navigation", lambda: None),
            patch.object(utils.auth, "can_access_page", lambda _key: False),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        failures = []
        for page_file in PAGE_FILES:
            app = AppTest.from_file(str(page_file)).run(timeout=20)
            if app.exception:
                failures.append(
                    f"{page_file.relative_to(PROJECT_ROOT)}: "
                    + " | ".join(str(item.value) for item in app.exception)
                )

        self.assertEqual(failures, [], "\n".join(failures))

    def test_production_pages_do_not_reload_shared_python_modules(self):
        protected_files = [
            PROJECT_ROOT / "pages" / "4_库存.py",
            PROJECT_ROOT / "pages" / "5_货柜安排.py",
            PROJECT_ROOT / "pages" / "10_财务.py",
            PROJECT_ROOT / "utils" / "auth" / "ui.py",
        ]

        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in protected_files
            if "reload(" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            offenders,
            [],
            "生产环境禁止 reload() 共享模块：" + ", ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
