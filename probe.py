import html
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

import m3u8
import requests


DEFAULT_TIMEOUT = 10
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SEGMENT_BYTES = 64 * 1024
MAX_VARIANT_DEPTH = 5
USER_AGENT = "m3u-helper/1.0"


class ProbeError(Exception):
    pass


def validate_url(url, allow_private=False):
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只支持 HTTP 或 HTTPS URL")
    hostname = (parsed.hostname or "").lower()
    if not allow_private and hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("出于安全原因不允许访问本机地址")
    if not allow_private and _host_is_private(hostname):
        raise ValueError("出于安全原因不允许访问内网地址")
    return url


def _host_is_private(hostname):
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            ]
        except socket.gaierror:
            return False
    return any(
        address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast
        for address in addresses
    )


def _empty_result(url, method, error):
    return {
        "url": url,
        "available": False,
        "method": method,
        "error": str(error),
        "format": {},
        "streams": [],
        "video": [],
        "audio": [],
        "playlist": {},
    }


def _stream_video(stream):
    width = stream.get("width")
    height = stream.get("height")
    item = {
        "codec": stream.get("codec_name") or stream.get("codec_tag_string") or "未知",
        "codec_long_name": stream.get("codec_long_name") or "",
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else "未知",
        "frame_rate": stream.get("r_frame_rate") or stream.get("avg_frame_rate") or "",
        "bit_rate": stream.get("bit_rate") or "",
    }
    return item


def _stream_audio(stream):
    return {
        "codec": stream.get("codec_name") or stream.get("codec_tag_string") or "未知",
        "codec_long_name": stream.get("codec_long_name") or "",
        "sample_rate": stream.get("sample_rate") or "",
        "channels": stream.get("channels"),
        "channel_layout": stream.get("channel_layout") or "",
        "bit_rate": stream.get("bit_rate") or "",
        "language": stream.get("tags", {}).get("language") or "",
    }


def normalize_ffprobe(data):
    streams = data.get("streams") or []
    video = [_stream_video(stream) for stream in streams if stream.get("codec_type") == "video"]
    audio = [_stream_audio(stream) for stream in streams if stream.get("codec_type") == "audio"]
    if not video and not audio:
        raise ProbeError("未发现音视频流")
    return {
        "available": True,
        "method": "ffprobe",
        "format": data.get("format") or {},
        "streams": streams,
        "video": video,
        "audio": audio,
        "playlist": {},
    }


def probe_with_ffprobe(url, timeout=DEFAULT_TIMEOUT, executable=None):
    executable = executable or shutil.which("ffprobe")
    if not executable:
        raise FileNotFoundError("系统中没有找到 ffprobe")
    command = [
        executable,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        url,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("ffprobe 探测超时") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "ffprobe 未返回有效结果").strip()
        raise ProbeError(detail[-1000:])
    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe 输出不是有效 JSON") from exc
    result = normalize_ffprobe(data)
    result["url"] = url
    return result


def parse_ffmpeg_output(stderr):
    text = stderr.decode(errors="replace") if isinstance(stderr, bytes) else str(stderr or "")
    video = []
    audio = []
    for line in text.splitlines():
        video_match = re.search(r"Video:\s*([^,\s]+)", line)
        if video_match:
            resolution_match = re.search(r"(\d{2,5})x(\d{2,5})", line)
            width = int(resolution_match.group(1)) if resolution_match else None
            height = int(resolution_match.group(2)) if resolution_match else None
            video.append(
                {
                    "codec": video_match.group(1),
                    "width": width,
                    "height": height,
                    "resolution": f"{width}x{height}" if width and height else "未知",
                }
            )
        audio_match = re.search(r"Audio:\s*([^,\s]+)", line)
        if audio_match:
            sample_match = re.search(r"(\d{3,6})\s*Hz", line)
            channels_match = re.search(r"(?:Hz,\s*)([^,\s]+)", line)
            audio.append(
                {
                    "codec": audio_match.group(1),
                    "sample_rate": sample_match.group(1) if sample_match else "",
                    "channels": channels_match.group(1) if channels_match else "",
                }
            )
    if not video and not audio:
        raise ProbeError("ffmpeg 输出中未发现音视频流")
    return {"video": video, "audio": audio}


def validate_ffmpeg_result(stderr, returncode):
    if returncode != 0:
        detail = str(stderr or "ffmpeg 未返回有效结果").strip()
        raise ProbeError(detail[-1000:])
    return parse_ffmpeg_output(stderr)


def probe_with_ffmpeg(url, timeout=DEFAULT_TIMEOUT, executable=None):
    executable = executable or shutil.which("ffmpeg")
    if not executable:
        raise FileNotFoundError("系统中没有找到 ffmpeg")
    command = [executable, "-hide_banner", "-i", url, "-t", "0", "-f", "null", "-"]
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
        streams = validate_ffmpeg_result(completed.stderr, completed.returncode)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("ffmpeg 探测超时") from exc
    return {
        "url": url,
        "available": True,
        "method": "ffmpeg",
        "format": {"format_name": "ffmpeg probe"},
        "streams": [],
        "video": streams["video"],
        "audio": streams["audio"],
        "playlist": {},
    }


def _read_response(response, max_bytes):
    chunks = []
    total = 0
    for chunk in response.iter_content(64 * 1024):
        if not chunk:
            continue
        remaining = max_bytes - total
        chunks.append(chunk[:remaining])
        total += min(len(chunk), remaining)
        if total >= max_bytes:
            break
    return b"".join(chunks)


def _fetch(url, timeout, max_bytes, allow_private=False):
    validate_url(url, allow_private=allow_private)
    try:
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            validate_url(response.url, allow_private=allow_private)
            return _read_response(response, max_bytes), response.url
    except requests.RequestException as exc:
        raise ProbeError(f"请求失败: {exc}") from exc


def _codec_parts(codecs):
    video_codecs = []
    audio_codecs = []
    for codec in (codecs or "").split(","):
        codec = codec.strip()
        if not codec:
            continue
        if codec.lower().startswith(("mp4a", "ac-3", "ec-3", "opus", "vorbis", "mp3")):
            audio_codecs.append(codec)
        else:
            video_codecs.append(codec)
    return video_codecs, audio_codecs


def _variant_video_audio(playlist):
    video = []
    audio = []
    for variant in playlist.playlists:
        info = variant.stream_info
        resolution = info.resolution
        width, height = resolution if resolution else (None, None)
        video_codecs, audio_codecs = _codec_parts(info.codecs)
        video_item = {
            "codec": video_codecs[0] if video_codecs else "未知",
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}" if width and height else "未知",
            "bandwidth": info.bandwidth,
            "url": variant.absolute_uri or variant.uri,
        }
        video.append(video_item)
        for codec in audio_codecs:
            audio.append({"codec": codec, "group": info.audio or "", "channels": ""})
        for media in playlist.media:
            if media.type == "AUDIO" and media.group_id == info.audio:
                audio.append(
                    {
                        "codec": audio_codecs[0] if audio_codecs else "未知",
                        "group": media.group_id or "",
                        "name": media.name or "",
                        "language": media.language or "",
                        "channels": media.channels or "",
                    }
                )
    unique_audio = []
    seen = set()
    for item in audio:
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            unique_audio.append(item)
    return video, unique_audio


def probe_m3u8(url, timeout=DEFAULT_TIMEOUT, allow_private=False):
    validate_url(url, allow_private=allow_private)
    try:
        content, final_url = _fetch(url, timeout, MAX_MANIFEST_BYTES, allow_private)
        if not content.lstrip().startswith(b"#EXTM3U"):
            raise ProbeError("响应内容不是 M3U8 播放列表")
        root = m3u8.loads(content.decode("utf-8-sig", errors="replace"), uri=final_url)
        root_is_variant = bool(root.playlists)
        video, audio = _variant_video_audio(root)
        current = root
        current_url = final_url
        depth = 0
        while current.playlists:
            if depth >= MAX_VARIANT_DEPTH:
                raise ProbeError(f"子播放列表嵌套超过 {MAX_VARIANT_DEPTH} 层")
            selected = max(current.playlists, key=lambda item: item.stream_info.bandwidth or 0)
            child_url = selected.absolute_uri
            child_content, child_final_url = _fetch(child_url, timeout, MAX_MANIFEST_BYTES, allow_private)
            current = m3u8.loads(child_content.decode("utf-8-sig", errors="replace"), uri=child_final_url)
            current_url = child_final_url
            depth += 1
        if not current.segments:
            raise ProbeError("播放列表没有媒体片段")
        segment = current.segments[-1]
        segment_url = segment.absolute_uri
        try:
            segment_content, _ = _fetch(segment_url, timeout, MAX_SEGMENT_BYTES, allow_private)
        except ProbeError as exc:
            raise ProbeError(f"媒体片段检查失败: {exc}") from exc
        if not segment_content:
            raise ProbeError("媒体片段为空")
        if not video and not audio:
            video = [{"codec": "未知", "resolution": "未知", "width": None, "height": None}]
        return {
            "url": url,
            "available": True,
            "method": "m3u8",
            "format": {"format_name": "hls"},
            "streams": [],
            "video": video,
            "audio": audio,
            "playlist": {
                "type": "master" if root_is_variant else "media",
                "variants": len(root.playlists),
                "checked_url": current_url,
                "segments": len(current.segments),
                "segment_url": segment_url,
                "segment_bytes": len(segment_content),
            },
        }
    except (ProbeError, UnicodeError, ValueError, AttributeError, KeyError) as exc:
        return _empty_result(url, "m3u8", exc)


def probe_url(url, timeout=DEFAULT_TIMEOUT, allow_private=False):
    validate_url(url, allow_private=allow_private)
    errors = []
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            return probe_with_ffprobe(url, timeout, ffprobe)
        except (ProbeError, OSError) as exc:
            errors.append(f"ffprobe: {exc}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            return probe_with_ffmpeg(url, timeout, ffmpeg)
        except (ProbeError, OSError) as exc:
            errors.append(f"ffmpeg: {exc}")
    result = probe_m3u8(url, timeout, allow_private=allow_private)
    if not result["available"] and errors:
        result["error"] = "; ".join(errors + [result["error"]])
    return result


def parse_m3u(content, base_url=None):
    if "#EXT-X-STREAM-INF" in content:
        playlist = m3u8.loads(content, uri=base_url)
        entries = []
        for index, variant in enumerate(playlist.playlists, start=1):
            resolution = variant.stream_info.resolution
            resolution_text = f"{resolution[0]}x{resolution[1]}" if resolution else "未知分辨率"
            entries.append(
                {
                    "duration": "-1",
                    "title": f"变体 {index} ({resolution_text})",
                    "url": variant.absolute_uri or variant.uri,
                    "resolution": resolution_text,
                    "bandwidth": variant.stream_info.bandwidth,
                    "codecs": variant.stream_info.codecs or "",
                }
            )
        return entries
    lines = content.splitlines()
    entries = []
    current_entry = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            info = line[8:].split(",", 1)
            current_entry = {"duration": info[0], "title": info[1] if len(info) > 1 else "", "url": ""}
        elif not line.startswith("#") and current_entry is not None:
            current_entry["url"] = line
            entries.append(current_entry)
            current_entry = None
    return entries


def _value(value):
    if value in (None, ""):
        return "未知"
    return html.escape(str(value))


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{_value(row.get(key))}</td>" for key in keys) + "</tr>" for keys, row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body or '<tr><td colspan=99>未发现</td></tr>'}</tbody></table>"


def render_html_report(result):
    available = bool(result.get("available"))
    status = "可用" if available else "不可用"
    status_class = "ok" if available else "bad"
    video_rows = [
        (
            ("codec", "resolution", "frame_rate", "bit_rate"),
            item,
        )
        for item in result.get("video", [])
    ]
    audio_rows = [
        (
            ("codec", "sample_rate", "channels", "channel_layout", "bit_rate", "language"),
            item,
        )
        for item in result.get("audio", [])
    ]
    playlist = result.get("playlist") or {}
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    error = f"<p class=error>{_value(result.get('error'))}</p>" if result.get("error") else ""
    playlist_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{_value(playlist.get(key))}</td></tr>"
        for key, label in (
            ("type", "播放列表类型"),
            ("variants", "变体数量"),
            ("checked_url", "检查的子清单"),
            ("segments", "片段数量"),
            ("segment_url", "检查的片段"),
            ("segment_bytes", "片段字节数"),
        )
        if key in playlist
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>M3U8 探测报告</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#1f2937}}
h1{{margin-bottom:.25rem}} table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}
th,td{{border:1px solid #d1d5db;padding:.5rem;text-align:left;word-break:break-word}}
th{{background:#f3f4f6}} .status{{font-size:1.25rem;font-weight:700}}
.ok{{color:#15803d}} .bad,.error{{color:#b91c1c}}
</style></head>
<body><h1>M3U8 探测报告</h1>
<p>生成时间（UTC）：{_value(generated_at)}</p>
<table><tbody>
<tr><th>URL</th><td>{_value(result.get('url'))}</td></tr>
<tr><th>可用性</th><td class="status {status_class}">{status}</td></tr>
<tr><th>探测方式</th><td>{_value(result.get('method'))}</td></tr>
</tbody></table>
{error}
<h2>视频信息</h2>{_table(("编码", "分辨率", "帧率", "比特率"), video_rows)}
<h2>音频信息</h2>{_table(("编码", "采样率", "声道", "声道布局", "比特率", "语言"), audio_rows)}
{f'<h2>播放列表检查</h2><table><tbody>{playlist_rows}</tbody></table>' if playlist_rows else ''}
</body></html>"""
