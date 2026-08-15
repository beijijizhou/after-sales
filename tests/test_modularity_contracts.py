import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ModularityContractTests(unittest.TestCase):
    def test_refactored_controllers_stay_small(self):
        limits = {
            "ui/logistics/page.py": 200,
            "ui/inventory/history/workflows/page.py": 220,
            "ui/inventory/planning/colored_consumption.py": 200,
            "db/inventory/container/tables.py": 200,
            "ui/inventory/operations/adjustment_preview.py": 200,
            "ui/inventory/operations/outbound.py": 200,
            "ui/inventory/operations/forms.py": 200,
            "ui/inventory/dashboard.py": 250,
            "ui/finance/page.py": 200,
            "ui/inventory/sales/page.py": 200,
            "ui/consumables/sku.py": 50,
            "ui/inventory/container/tables.py": 150,
            "ui/inventory/container/page.py": 150,
            "ui/inventory/container/transit_view.py": 150,
            "ui/inventory/shared/filters.py": 220,
        }
        for relative, limit in limits.items():
            with self.subTest(file=relative):
                self.assertLessEqual(_line_count(relative), limit)

    def test_logistics_directories_keep_focused_file_counts(self):
        expected = {
            "ui/logistics": 5,
            "ui/logistics/review": 5,
            "ui/logistics/summary": 5,
            "ui/logistics/tracking": 5,
        }
        for relative, maximum in expected.items():
            with self.subTest(directory=relative):
                self.assertLessEqual(len(_core_python_files(relative)), maximum)

    def test_inventory_history_subdirectories_keep_focused_file_counts(self):
        expected = {
            "ui/inventory/history/core": 5,
            "ui/inventory/history/workflows": 5,
        }
        for relative, maximum in expected.items():
            with self.subTest(directory=relative):
                self.assertLessEqual(len(_core_python_files(relative)), maximum)

    def test_refactored_domain_files_remain_near_two_hundred_lines(self):
        directories = (
            "ui/logistics/review",
            "ui/logistics/tracking",
            "ui/inventory/history/core",
            "ui/inventory/history/workflows",
        )
        for directory in directories:
            for path in _core_python_files(directory):
                with self.subTest(file=str(path.relative_to(PROJECT_ROOT))):
                    self.assertLessEqual(len(path.read_text().splitlines()), 250)

    def test_new_shared_domain_modules_remain_focused(self):
        files = (
            "db/finance/consumable_repository.py",
            "db/finance/cost_maintenance.py",
            "db/inventory/container/input_tables.py",
            "db/inventory/container/summary_tables.py",
            "db/inventory/operations/outbound_specs.py",
            "db/inventory/operations/outbound_verification.py",
            "db/inventory/planning/incoming_containers.py",
            "db/inventory/planning/incoming_views.py",
            "ui/inventory/operations/inventory_review.py",
            "ui/inventory/operations/adjustment_editor.py",
            "ui/inventory/planning/colored_review.py",
            "ui/inventory/planning/uv_view.py",
            "automation/sync/daily_flow_preview.py",
            "db/inventory/dashboard_overview.py",
            "db/inventory/dashboard_completion.py",
            "ui/inventory/dashboard_overview.py",
            "ui/inventory/dashboard_batch_view.py",
            "ui/inventory/operations/outbound_entry.py",
            "ui/inventory/operations/outbound_import.py",
            "ui/inventory/operations/outbound_review.py",
            "ui/inventory/container/detail_tables.py",
            "ui/inventory/container/summary_tables.py",
            "ui/consumables/sku_models.py",
            "ui/consumables/sku_create.py",
            "ui/consumables/sku_catalog.py",
            "ui/inventory/sales/customer_section.py",
            "ui/inventory/sales/invoice_review.py",
            "ui/consumables/operations/stock_models.py",
            "ui/inventory/operations/sku_creation.py",
            "ui/inventory/shared/filter_models.py",
        )
        for relative in files:
            with self.subTest(file=relative):
                self.assertLessEqual(_line_count(relative), 250)

    def test_function_catalog_documents_cross_page_reuse_gate(self):
        catalog = (PROJECT_ROOT / "docs/FUNCTION_CATALOG.md").read_text()
        self.assertIn("## Page Capabilities", catalog)
        self.assertIn("## Shared Capability Registry", catalog)
        self.assertIn("## Reuse Review Gate", catalog)


def _line_count(relative):
    return len((PROJECT_ROOT / relative).read_text().splitlines())


def _core_python_files(relative):
    return [
        path for path in (PROJECT_ROOT / relative).glob("*.py")
        if path.name != "__init__.py"
    ]


if __name__ == "__main__":
    unittest.main()
