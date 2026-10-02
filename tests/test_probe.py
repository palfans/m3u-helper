import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from probe import (
    normalize_ffprobe,
    capture_thumbnail,
    parse_ffmpeg_output,
    parse_m3u,
    probe_m3u8,
    ProbeError,
    render_html_report,
    fetch_m3u_content,
    validate_url,
    validate_ffmpeg_result,
)


class PlaylistHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        if self.path == "/redirect.m3u8":
            self.send_response(302)
            self.send_header("Location", "/master.m3u8")
            self.end_headers()
            return
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
                '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio-main",NAME="主音轨",URI="audio/index.m3u8"',
                '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subtitle-main",NAME="中文字幕",URI="sub/index.m3u8"',
                '#EXT-X-STREAM-INF:BANDWIDTH=2200000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2",AUDIO="audio-main",SUBTITLES="subtitle-main"',
                "video/720/index.m3u8",
            ]
        )

        entries = parse_m3u(content, "https://cdn.example/root.m3u8")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://cdn.example/video/720/index.m3u8")
        self.assertEqual(entries[0]["resolution"], "1280x720")
        self.assertEqual(entries[0]["groups"], ["audio-main", "subtitle-main"])

    def test_parse_m3u_keeps_iptv_group_title(self):
        content = "\n".join(
            [
                "#EXTM3U",
                '#EXTINF:-1 tvg-id="news" group-title="新闻,综合",频道一',
                "https://cdn.example/news/index.m3u8",
            ]
        )

        entries = parse_m3u(content)

        self.assertEqual(entries[0]["groups"], ["新闻,综合"])

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

        result = probe_m3u8(f"{self.base_url}/master.m3u8", timeout=2, allow_private=True)

        self.assertTrue(result["available"])
        self.assertEqual(result["method"], "m3u8")
        self.assertEqual(result["video"][0]["resolution"], "1280x720")
        self.assertEqual(result["audio"][0]["codec"], "mp4a.40.2")
        self.assertEqual(result["playlist"]["segment_bytes"], 32)

    def test_manifest_fetch_follows_redirect(self):
        PlaylistHandler.routes = {
            "/master.m3u8": (b"#EXTM3U\n", 200, "application/vnd.apple.mpegurl"),
        }

        content, final_url = fetch_m3u_content(
            f"{self.base_url}/redirect.m3u8",
            timeout=2,
            allow_private=True,
        )

        self.assertEqual(content, "#EXTM3U\n")
        self.assertEqual(final_url, f"{self.base_url}/master.m3u8")

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

        result = probe_m3u8(f"{self.base_url}/master.m3u8", timeout=2, allow_private=True)

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

    def test_ffmpeg_nonzero_exit_is_not_available(self):
        with self.assertRaises(ProbeError):
            validate_ffmpeg_result("Stream #0:0: Video: h264, 1920x1080", 1)

    def test_capture_thumbnail_reports_ffmpeg_failure(self):
        with self.assertRaises(ProbeError):
            capture_thumbnail("https://example.test/live.m3u8", timeout=1, executable="/bin/false")

    def test_private_url_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            validate_url("http://127.0.0.1:8080/live.m3u8")

        self.assertEqual(
            validate_url("http://127.0.0.1:8080/live.m3u8", allow_private=True),
            "http://127.0.0.1:8080/live.m3u8",
        )

    def test_render_html_report_escapes_values(self):
        result = {
            "url": "https://example.test/?q=<unsafe>",
            "available": True,
            "method": "ffprobe",
            "video": [{"codec": "h264", "resolution": "1280x720"}],
            "audio": [{"codec": "aac", "sample_rate": "48000", "channels": 2}],
            "playlist": {},
            "thumbnail": "data:image/jpeg;base64,ZmFrZQ==",
        }

        html = render_html_report(result)

        self.assertIn("可用", html)
        self.assertIn("1280x720", html)
        self.assertIn("48000", html)
        self.assertIn('class="thumbnail-preview"', html)
        self.assertIn("data:image/jpeg;base64,ZmFrZQ==", html)
        self.assertIn("&lt;unsafe&gt;", html)
        self.assertNotIn("?q=<unsafe>", html)


if __name__ == "__main__":
    unittest.main()
