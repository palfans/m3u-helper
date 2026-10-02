import io
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import app


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
        self.client = app.test_client()

    def test_parse_master_m3u8_returns_variant_entry(self):
        response = self.client.post("/parse", data={"url": self.url})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["entries"][0]["resolution"], "1280x720")
        self.assertTrue(data["entries"][0]["url"].endswith("/video/index.m3u8"))

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

    def test_video_info_rejects_missing_json_body(self):
        response = self.client.post("/video-info", data="bad", content_type="text/plain")

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON", response.get_json()["error"])

    def test_json_endpoints_reject_non_object_bodies(self):
        for path in ("/video-info", "/report", "/check-all", "/download"):
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


if __name__ == "__main__":
    unittest.main()
