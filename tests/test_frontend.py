import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def test_page_exposes_report_action(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="reportBtn"', page)

    def test_page_exposes_dashboard_controls(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        for element_id in (
            "summaryTotal",
            "summaryAvailable",
            "summaryErrors",
            "summaryPending",
            "playlistSearch",
            "statusFilter",
            "progressPanel",
            "emptyState",
            "toastContainer",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', page)

    def test_page_uses_local_visual_styles(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="/static/css/style.css"', page)
        self.assertTrue((ROOT / "static" / "css" / "style.css").exists())

    def test_script_uses_batch_check_and_report_endpoints(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("fetch('/check-all'", script)
        self.assertIn("fetch('/report'", script)

    def test_script_cleans_stale_results_and_blob_urls(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("URL.revokeObjectURL", script)
        self.assertIn("clearStaleState", script)
        self.assertIn("applyFilters", script)

    def test_script_guards_stale_parse_cleanup(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn(
            "if (state.parseController === controller) {\n                state.parseController = null;\n                setParsingState(false);",
            script,
        )
        self.assertIn("state.reportController?.abort();", script)
        self.assertIn("state.downloadController?.abort();", script)


if __name__ == "__main__":
    unittest.main()
