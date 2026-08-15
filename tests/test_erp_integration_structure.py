from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ErpIntegrationStructureTests(unittest.TestCase):
    def test_provider_logistics_modules_are_compatibility_only(self):
        for provider in ("humbird", "sds", "s2b", "diy19"):
            path = ROOT / "automation" / "logistics" / f"{provider}.py"
            source = path.read_text(encoding="utf-8")
            self.assertIn("Compatibility", source, provider)
            self.assertNotIn("https://", source, provider)
            self.assertLessEqual(len(source.splitlines()), 25, provider)

    def test_provider_packages_own_production_and_shipment_modules(self):
        for provider in ("humbird", "sds", "s2b", "diy19"):
            directory = ROOT / "automation" / "api" / provider
            self.assertTrue((directory / "client.py").is_file(), provider)
            self.assertTrue((directory / "shipments.py").is_file(), provider)

    def test_shared_integration_layer_has_no_provider_http_endpoints(self):
        directory = ROOT / "automation" / "integrations"
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in directory.glob("*.py")
        )
        self.assertNotIn("https://", source)


if __name__ == "__main__":
    unittest.main()
