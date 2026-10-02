import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def test_page_exposes_report_action(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="reportBtn"', page)

    def test_script_uses_batch_check_and_report_endpoints(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("fetch('/check-all'", script)
        self.assertIn("fetch('/report'", script)


if __name__ == "__main__":
    unittest.main()
