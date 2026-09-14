from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from audio_transcript.transcription import TranscriptionCancelled


def normalize_youtube_url(value: str) -> str:
    """Accept one YouTube video, stripping playlist, tracking and timestamp parameters."""
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.port:
            raise ValueError
        parts = parsed.path.strip("/").split("/")
        host = (parsed.hostname or "").lower()
        if host in {"youtu.be", "www.youtu.be"} and len(parts) == 1:
            video_id = parts[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                video_id = parts[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
    except ValueError:
        raise ValueError("Paste a YouTube video link (watch, youtu.be, or Shorts), not a playlist or channel.") from None
    return f"https://www.youtube.com/watch?v={video_id}"


@dataclass(frozen=True, slots=True)
class DownloadedAudio:
    path: Path
    title: str


def download_audio(
    url: str,
    directory: Path,
    *,
    on_progress: Callable[[int], None],
    should_stop: Callable[[], bool],
) -> DownloadedAudio:
    """Download audio only into a caller-owned temporary directory."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = normalize_youtube_url(url)

    def check_stop() -> None:
        if should_stop():
            raise TranscriptionCancelled("YouTube download was stopped.")

    class Logger:
        def debug(self, message: str) -> None:
            check_stop()

        info = warning = error = debug

    def progress(data: dict) -> None:
        check_stop()
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        percent = min(99, int(100 * data.get("downloaded_bytes", 0) / total)) if total else -1
        on_progress(100 if data.get("status") == "finished" else percent)

    def reject_live(info: dict, *, incomplete: bool = False) -> str | None:
        check_stop()
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
            raise RuntimeError("Live and upcoming streams are not supported. Use a finished video.")
        return None

    check_stop()
    runtimes = {name: {"path": path} for name in ("deno", "node") if (path := shutil.which(name))}
    if not runtimes:
        raise RuntimeError("YouTube needs Node.js 22+ or Deno 2.3+ on PATH. See README setup instructions.")
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "outtmpl": str(directory / "audio.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "logger": Logger(),
        "progress_hooks": [progress],
        "match_filter": reject_live,
        "break_on_reject": True,
        "cachedir": False,
        "js_runtimes": runtimes,
        "remote_components": set(),
        "socket_timeout": 15,
        "retries": 2,
        "extractor_retries": 2,
        "fragment_retries": 2,
        "skip_unavailable_fragments": False,
        "fixup": "never",
        "windowsfilenames": True,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            check_stop()
            if not info or info.get("_type", "video") != "video":
                raise RuntimeError("No downloadable video was found.")
            path = Path(downloader.prepare_filename(info)).resolve()
            if path.parent != directory.resolve() or not path.is_file():
                raise RuntimeError("YouTube did not produce a complete audio file.")
            title = " ".join(str(info.get("title") or "YouTube video").split())
            return DownloadedAudio(path, title)
    except DownloadError as exc:
        check_stop()
        raise RuntimeError(
            "Could not download YouTube audio. Check your connection and that the video is available "
            "without signing in. If this persists, update yt-dlp as described in README.\n\n"
            f"Details: {exc}"
        ) from exc
