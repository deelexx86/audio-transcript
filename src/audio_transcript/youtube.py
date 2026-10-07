from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections import deque
from importlib.metadata import PackageNotFoundError, version
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from audio_transcript.transcription import TranscriptionCancelled


RETRY_DELAY_SECONDS = 10.0


def failure_kind(message: str) -> str:
    text = message.casefold().replace("’", "'")
    if "not a bot" in text or "confirm you're" in text and "bot" in text:
        return "bot_check"
    if any(term in text for term in ("private video", "members-only", "age-restricted", "confirm your age", "sign in")):
        return "access_restricted"
    if "requested format" in text or "no video formats" in text:
        return "formats"
    if any(term in text for term in ("video unavailable", "not available", "removed", "copyright")):
        return "unavailable"
    if any(term in text for term in ("javascript runtime", "challenge solver", "yt-dlp-ejs")):
        return "components"
    if any(term in text for term in ("timed out", "timeout", "connection", "resolve", "network", "http error 429", "http error 5")):
        return "network"
    if "403" in text or "forbidden" in text:
        return "request_rejected"
    return "download_failed"


ERROR_MESSAGES = {
    "bot_check": "YouTube requested an anti-bot check for this download. The video may still play publicly in a browser. One automatic retry was unsuccessful. Try Retry Selected later; signing in or updating is not a guaranteed fix.",
    "access_restricted": "YouTube reported an access restriction (such as sign-in, age, or membership). This app does not use accounts or browser cookies.",
    "unavailable": "YouTube reported that this video is unavailable or restricted in this location.",
    "components": "YouTube downloader components are missing or unsupported. Check Node.js 22+ or Deno 2.3+ and the matching yt-dlp[default] installation in README.",
    "network": "The YouTube request failed because of a connection, timeout, or server/rate-limit error. Check connectivity and try Retry Selected later.",
    "request_rejected": "YouTube rejected the media request (HTTP 403). This does not establish that the video requires login. Try later; see README for downloader troubleshooting.",
    "formats": "YouTube returned no usable audio format. This does not establish that the video is unavailable. Check the component versions and warning summaries below.",
    "download_failed": "The YouTube download failed. See the diagnostic summary below and README troubleshooting.",
}


class YouTubeDownloadError(RuntimeError):
    def __init__(self, kind: str, stage: str, attempts: int, components: str, warnings: list[str]):
        self.kind = kind
        self.attempts = attempts
        details = [f"Category: {kind}", f"Stage: {stage}", f"Attempts: {attempts}", components]
        if warnings:
            details.append("Warnings: " + "; ".join(warnings))
        super().__init__(ERROR_MESSAGES[kind] + "\n\nDiagnostics:\n" + "\n".join(details))


def component_summary(runtimes: dict) -> str:
    versions = []
    for package in ("yt-dlp", "yt-dlp-ejs"):
        try:
            value = version(package)
        except PackageNotFoundError:
            value = "missing"
        versions.append(f"{package}: {value}")
    for name, config in runtimes.items():
        try:
            result = subprocess.run(
                [config["path"], "--version"], capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            match = re.search(r"(?<!\d)\d+\.\d+\.\d+\b", result.stdout)
            value = match.group() if match else "version unavailable"
        except (OSError, subprocess.SubprocessError):
            value = "unavailable"
        versions.append(f"{name}: {value}")
    return "; ".join(versions)


def wait_to_retry(should_stop: Callable[[], bool]) -> None:
    deadline = time.monotonic() + RETRY_DELAY_SECONDS
    while True:
        if should_stop():
            raise TranscriptionCancelled("YouTube retry was stopped.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


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
    on_retry: Callable[[], None] = lambda: None,
) -> DownloadedAudio:
    """Download audio only into a caller-owned temporary directory."""
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError:
        raise YouTubeDownloadError("components", "downloader setup", 0, component_summary({}), []) from None

    url = normalize_youtube_url(url)
    stage = "video information"
    warnings: deque[str] = deque(maxlen=5)

    def check_stop() -> None:
        if should_stop():
            raise TranscriptionCancelled("YouTube download was stopped.")

    class Logger:
        def debug(self, message: str) -> None:
            nonlocal stage
            check_stop()
            if "Downloading webpage" in message:
                stage = "video webpage"
            elif "player" in message and "Downloading" in message:
                stage = "player information"
            elif "m3u8" in message and "Downloading" in message:
                stage = "audio manifest"

        info = debug

        def warning(self, message: str) -> None:
            check_stop()
            # Only fixed summaries are retained, never URLs, headers, cookies or raw logs.
            text = message.casefold()
            summary = None
            if "po token" in text or "po_token" in text:
                summary = "Some formats require a PO token"
            elif "javascript" in text or "challenge" in text or "yt-dlp-ejs" in text:
                summary = "JavaScript challenge/runtime warning"
            elif "format" in text:
                summary = "Some media formats are unavailable"
            elif "retry" in text or "timed out" in text:
                summary = "A request needed retrying"
            if summary and summary not in warnings:
                warnings.append(summary)

        error = warning

    def progress(data: dict) -> None:
        nonlocal stage
        check_stop()
        stage = "audio transfer"
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
        raise YouTubeDownloadError("components", "runtime setup", 0, component_summary(runtimes), [])
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
    for attempt in (1, 2):
        check_stop()
        stage = "video information"
        try:
            # A new instance creates a fresh guest session for the single retry.
            with YoutubeDL(options.copy()) as downloader:
                info = downloader.extract_info(url, download=True)
                check_stop()
                if not info or info.get("_type", "video") != "video":
                    raise DownloadError("No downloadable video was found.")
                path = Path(downloader.prepare_filename(info)).resolve()
                if path.parent != directory.resolve() or not path.is_file():
                    raise DownloadError("YouTube did not produce a complete audio file.")
                title = " ".join(str(info.get("title") or "YouTube video").split())
                return DownloadedAudio(path, title)
        except DownloadError as exc:
            check_stop()
            kind = failure_kind(str(exc))
            if kind == "bot_check" and attempt == 1:
                on_retry()
                wait_to_retry(should_stop)
                on_progress(-1)
                continue
            raise YouTubeDownloadError(kind, stage, attempt, component_summary(runtimes), list(warnings)) from None
