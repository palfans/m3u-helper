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
            "groupFilter",
            "selectedCount",
            "checkSelectedBtn",
            "stopCheckBtn",
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

        self.assertIn("fetchResponse('/check-all'", script)
        self.assertIn("fetchResponse('/report'", script)
        self.assertIn("fetchResponse('/thumbnail'", script)
        self.assertIn("body: JSON.stringify({ entries: batch, workers })", script)

    def test_script_supports_group_filtering_and_scoped_checks(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn('id="groupFilter"', page)
        self.assertIn("entryGroups", script)
        self.assertIn("getGroupIndexes", script)
        self.assertIn("state.groupFilter", script)
        self.assertIn("const scopeIndexes = getGroupIndexes();", script)

    def test_script_supports_manual_selection_checks(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("entry-select", script)
        self.assertIn('id="selectedCount"', page)
        self.assertIn('id="checkSelectedBtn"', page)
        self.assertIn("state.selected", script)
        self.assertIn("const scopeIndexes = Array.from(state.selected)", script)
        self.assertIn("checkSelected", script)

    def test_script_supports_single_entry_checks(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("makeButton('检查', 'small-button check-button'", script)
        self.assertIn("function checkEntry(index)", script)
        self.assertIn("return runCheck([index]);", script)
        self.assertIn("checkEntry(index)", script)

    def test_page_exposes_floating_selection_action(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn('id="selectionFloat"', page)
        self.assertIn('class="selection-float is-hidden"', page)
        self.assertNotIn('class="selection-actions"', page)
        self.assertIn("selectionFloat: get('selectionFloat')", script)
        self.assertIn("dom.selectionFloat.classList.toggle('is-hidden', selected === 0);", script)
        self.assertIn(".selection-float", styles)

    def test_script_supports_stopping_checks(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn('id="stopCheckBtn"', page)
        self.assertIn("stopCheckButton: get('stopCheckBtn')", script)
        self.assertIn("state.stopRequested", script)
        self.assertIn("state.checkController?.abort();", script)
        self.assertIn("function stopCheck()", script)
        self.assertIn("dom.stopCheckButton.addEventListener('click', stopCheck);", script)

    def test_styles_increase_reading_sizes(self):
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".item-title-group h3 {\n    overflow: hidden;\n    margin: 2px 0 7px;\n    color: var(--ink);\n    font-size: 16px;", styles)
        self.assertIn(".item-url {\n    display: block;", styles)
        self.assertIn("    font-size: 12px;\n    text-overflow: ellipsis;", styles)

    def test_script_renders_on_demand_thumbnail(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn("thumbnail-preview", script)
        self.assertIn("thumbnail_error", script)
        self.assertIn(".thumbnail-preview", styles)

    def test_script_batches_long_check_requests(self):
        script = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("const batchSize = Math.max(1, workers * 2);", script)
        self.assertIn("for (let start = 0; start < scopeIndexes.length; start += batchSize)", script)
        self.assertIn("const batch = batchIndexes.map((index) => state.entries[index]);", script)
        self.assertIn("state.results[index] = data.results[offset];", script)
        self.assertIn("连接失败", script)

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

    def test_page_keeps_secondary_copy_in_hover_text(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        for removed_copy in (
            "PLAYLIST INSPECTOR",
            "默认单线程，按列表顺序执行",
            "已确认可播放",
            "需要进一步处理",
            "等待顺序探测",
            "清晰检查每一个播放地址",
        ):
            self.assertNotIn(removed_copy, page)
        self.assertIn('title="按所选并发数检查所有条目"', page)
        self.assertIn('title="当前播放列表的总条目数"', page)

    def test_page_exposes_concurrency_selector(self):
        page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('id="pageTitle"', page)
        self.assertIn('id="checkWorkers"', page)
        for option in ('value="1"', 'value="2"', 'value="3"', 'value="5"'):
            with self.subTest(option=option):
                self.assertIn(option, page)

    def test_styles_use_light_theme_palette(self):
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn("--page: #f4f7fb", styles)
        self.assertNotIn("--page: #0b1324", styles)


if __name__ == "__main__":
    unittest.main()
