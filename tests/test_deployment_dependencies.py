import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeploymentDependencyTests(unittest.TestCase):
    def test_cloud_uses_headless_opencv_without_apt_packages(self):
        self.assertFalse(
            (PROJECT_ROOT / "packages.txt").exists(),
            "packages.txt triggers the currently broken Streamlit apt repository",
        )

        requirements = {
            line.strip()
            for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("opencv-python-headless==5.0.0.93", requirements)
        self.assertIn("./vendor/opencv_python_headless_alias", requirements)

    def test_rapidocr_opencv_alias_resolves_to_headless_build(self):
        alias_config = (
            PROJECT_ROOT
            / "vendor"
            / "opencv_python_headless_alias"
            / "pyproject.toml"
        ).read_text()

        self.assertIn('name = "opencv-python"', alias_config)
        self.assertIn('version = "5.0.0.93"', alias_config)
        self.assertIn('"opencv-python-headless==5.0.0.93"', alias_config)


if __name__ == "__main__":
    unittest.main()
