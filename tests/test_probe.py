import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from probe import normalize_ffprobe, parse_ffmpeg_output, parse_m3u, probe_m3u8, render_html_report


class PlaylistHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        body, status, content_type = self.routes.get(self.path, (b"", 404, "text/plain"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlaylistHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def test_parse_m3u_master_playlist_returns_variant_entries(self):
        content = "\n".join(
            [
                "#EXTM3U",
                '#EXT-X-STREAM-INF:BANDWIDTH=2200000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"',
                "video/720/index.m3u8",
            ]
        )

        entries = parse_m3u(content, "https://cdn.example/root.m3u8")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://cdn.example/video/720/index.m3u8")
        self.assertEqual(entries[0]["resolution"], "1280x720")

    def test_manifest_probe_follows_variant_and_checks_segment(self):
        PlaylistHandler.routes = {
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

        result = probe_m3u8(f"{self.base_url}/master.m3u8", timeout=2)

        self.assertTrue(result["available"])
        self.assertEqual(result["method"], "m3u8")
        self.assertEqual(result["video"][0]["resolution"], "1280x720")
        self.assertEqual(result["audio"][0]["codec"], "mp4a.40.2")
        self.assertEqual(result["playlist"]["segment_bytes"], 32)

    def test_manifest_probe_reports_failed_segment(self):
        PlaylistHandler.routes = {
            "/master.m3u8": (
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2200000,RESOLUTION=1280x720\nvideo/index.m3u8\n",
                200,
                "application/vnd.apple.mpegurl",
            ),
            "/video/index.m3u8": (
                b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nmissing.ts\n",
                200,
                "application/vnd.apple.mpegurl",
            ),
        }

        result = probe_m3u8(f"{self.base_url}/master.m3u8", timeout=2)

        self.assertFalse(result["available"])
        self.assertIn("媒体片段", result["error"])

    def test_normalize_ffprobe_includes_video_and_audio(self):
        result = normalize_ffprobe(
            {
                "format": {"format_name": "hls", "duration": "12.5"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
                ],
            }
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["video"][0]["resolution"], "1920x1080")
        self.assertEqual(result["audio"][0]["sample_rate"], "48000")
        self.assertEqual(result["audio"][0]["channels"], 2)

    def test_parse_ffmpeg_output_extracts_stream_basics(self):
        stderr = "\n".join(
            [
                "Input #0, hls, from 'x.m3u8':",
                "  Stream #0:0: Video: h264, yuv420p, 1920x1080, 25 fps",
                "  Stream #0:1: Audio: aac, 48000 Hz, stereo",
            ]
        )

        result = parse_ffmpeg_output(stderr)

        self.assertEqual(result["video"][0]["codec"], "h264")
        self.assertEqual(result["video"][0]["resolution"], "1920x1080")
        self.assertEqual(result["audio"][0]["codec"], "aac")
        self.assertEqual(result["audio"][0]["sample_rate"], "48000")

    def test_render_html_report_escapes_values(self):
        result = {
            "url": "https://example.test/?q=<unsafe>",
            "available": True,
            "method": "ffprobe",
            "video": [{"codec": "h264", "resolution": "1280x720"}],
            "audio": [{"codec": "aac", "sample_rate": "48000", "channels": 2}],
            "playlist": {},
        }

        html = render_html_report(result)

        self.assertIn("可用", html)
        self.assertIn("1280x720", html)
        self.assertIn("48000", html)
        self.assertIn("&lt;unsafe&gt;", html)
        self.assertNotIn("?q=<unsafe>", html)


if __name__ == "__main__":
    unittest.main()
