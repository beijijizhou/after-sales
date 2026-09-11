import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeploymentDependencyTests(unittest.TestCase):
    def test_opencv_linux_runtime_libraries_are_installed(self):
        packages = {
            line.strip()
            for line in (PROJECT_ROOT / "packages.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertIn("libgl1", packages)
        self.assertIn("libglib2.0-0t64", packages)


if __name__ == "__main__":
    unittest.main()
