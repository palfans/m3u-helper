import io
import logging
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import app, generate_m3u


ROOT = Path(__file__).resolve().parents[1]


class AppPlaylistHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/master.m3u8": (
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2200000,RESOLUTION=1280x720,CODECS=\"avc1.64001f,mp4a.40.2\"\nvideo/index.m3u8\n",
                200,
                "application/vnd.apple.mpegurl",
            ),
            "/video/index.m3u8": (
                b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nsegment.ts\n",
                200,
                "application/vnd.apple.mpegurl",
            ),
            "/video/segment.ts": (b"\x47" + b"x" * 31, 200, "video/mp2t"),
        }
        body, status, content_type = routes.get(self.path, (b"", 404, "text/plain"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AppPlaylistHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/master.m3u8"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        app.config["ALLOW_PRIVATE_URLS"] = True
        app.config["PROBE_TIMEOUT"] = 1
        app.config["CHECK_WORKERS"] = 1
        self.client = app.test_client()

    def test_parse_master_m3u8_returns_variant_entry(self):
        response = self.client.post("/parse", data={"url": self.url})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["entries"][0]["resolution"], "1280x720")
        self.assertTrue(data["entries"][0]["url"].endswith("/video/index.m3u8"))

    def test_generate_m3u_preserves_group_title(self):
        content = generate_m3u(
            [{"duration": "-1", "title": "频道一", "url": "https://example.test/one.m3u8", "groups": ["新闻"]}]
        )

        self.assertIn('#EXTINF:-1 group-title="新闻",频道一', content)

    def test_parse_remote_failure_is_written_to_application_log(self):
        missing_url = self.url.replace("/master.m3u8", "/missing.m3u8")

        with self.assertLogs("app", level="WARNING") as captured:
            response = self.client.post("/parse", data={"url": missing_url})

        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("parse remote playlist failed" in line for line in captured.output))

    def test_report_endpoint_returns_html(self):
        response = self.client.post("/report", json={"url": self.url})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn("M3U8", response.get_data(as_text=True))
        self.assertIn("1280x720", response.get_data(as_text=True))

    def test_check_all_keeps_invalid_entry_in_results(self):
        response = self.client.post(
            "/check-all",
            json={"entries": [{"title": "bad", "url": "ftp://example.test/live.m3u8"}]},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["status"], "error")

    def test_check_all_logs_video_progress_at_info(self):
        entry = {"title": "坏地址", "url": "ftp://example.test/live.m3u8"}

        with self.assertLogs("app", level="INFO") as captured:
            response = self.client.post("/check-all", json={"entries": [entry]})

        self.assertEqual(response.status_code, 200)
        output = "\n".join(captured.output)
        self.assertIn("check video started: title=坏地址", output)
        self.assertIn("check video completed: title=坏地址", output)
        self.assertIn("status=error", output)
        self.assertIn("method=validation", output)

    def test_request_details_are_logged_at_debug(self):
        with self.assertLogs("app", level="DEBUG") as captured:
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        request_records = [
            record for record in captured.records if record.getMessage().startswith("request:")
        ]
        self.assertEqual(len(request_records), 1)
        self.assertEqual(request_records[0].levelno, logging.DEBUG)
        self.assertIn("method=GET path=/ status=200", request_records[0].getMessage())

    def test_gunicorn_access_log_is_disabled(self):
        config = (ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")

        self.assertIn("accesslog = None", config)

    def test_check_all_worker_count_is_configurable(self):
        app.config["CHECK_WORKERS"] = 2
        try:
            response = self.client.post(
                "/check-all",
                json={
                    "entries": [
                        {"title": "one", "url": "ftp://example.test/one.m3u8"},
                        {"title": "two", "url": "ftp://example.test/two.m3u8"},
                    ]
                },
            )
        finally:
            app.config["CHECK_WORKERS"] = 1

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 2)

    def test_check_all_accepts_worker_count_from_request(self):
        response = self.client.post(
            "/check-all",
            json={
                "workers": 2,
                "entries": [{"title": "one", "url": "ftp://example.test/one.m3u8"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 1)

    def test_check_all_rejects_unsupported_worker_count(self):
        response = self.client.post(
            "/check-all",
            json={
                "workers": 4,
                "entries": [{"title": "one", "url": "ftp://example.test/one.m3u8"}],
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_video_info_rejects_missing_json_body(self):
        response = self.client.post("/video-info", data="bad", content_type="text/plain")

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON", response.get_json()["error"])

    def test_input_errors_return_bad_request(self):
        response = self.client.post("/video-info", json={"url": 123})
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/video-info", json={})
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/parse", data={"url": "ftp://example.test/list.m3u8"})
        self.assertEqual(response.status_code, 400)

    def test_json_endpoints_reject_non_object_bodies(self):
        for path in ("/video-info", "/thumbnail", "/report", "/check-all", "/download"):
            with self.subTest(path=path):
                response = self.client.post(path, json=[])
                self.assertEqual(response.status_code, 400)
                self.assertIn("对象", response.get_json()["error"])

    def test_upload_rejects_invalid_encoding(self):
        response = self.client.post(
            "/parse",
            data={"file": (io.BytesIO(bytes([0xFF])), "playlist.m3u8")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("编码", response.get_json()["error"])

        response = self.client.post(
            "/parse",
            data={"file": (io.BytesIO(b""), "")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
