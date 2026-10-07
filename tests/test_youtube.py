from pathlib import Path

import pytest

from audio_transcript.queueing import QueueManager
from audio_transcript.transcription import TranscriptionCancelled
from audio_transcript.youtube import download_audio, normalize_youtube_url


VIDEO_ID = "jNQXAC9IVRw"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize("value", [
    URL, f" https://youtu.be/{VIDEO_ID}?si=tracking ",
    f"youtube.com/watch?v={VIDEO_ID}&list=playlist&t=5",
    f"https://m.youtube.com/shorts/{VIDEO_ID}",
    f"https://www.youtube.com/embed/{VIDEO_ID}",
    f"https://youtube.com/live/{VIDEO_ID}",
    f"https://music.youtube.com/watch?v={VIDEO_ID}",
])
def test_normalize_video_links(value):
    assert normalize_youtube_url(value) == URL


@pytest.mark.parametrize("value", [
    "", "not a url", "https://youtube.com/playlist?list=abc", "https://youtube.com/@channel",
    "https://youtube.com/watch?v=invalid", f"https://youtube.com.evil.test/watch?v={VIDEO_ID}",
    f"https://youtube.com@evil.test/watch?v={VIDEO_ID}", f"https://user@youtube.com/watch?v={VIDEO_ID}",
    f"file://youtube.com/watch?v={VIDEO_ID}", f"https://youtube.com:8000/watch?v={VIDEO_ID}",
    "https://[invalid", f"https://youtu.be/{VIDEO_ID}/extra",
])
def test_reject_non_video_and_non_youtube_urls(value):
    with pytest.raises(ValueError, match="YouTube video link"):
        normalize_youtube_url(value)


def test_url_queue_deduplicates_aliases_and_releases_removed_ids():
    queue = QueueManager()
    item = queue.add_youtube(URL, " Speaker ")
    assert item.source_url == URL
    assert item.speaker == "Speaker"
    assert queue.add_youtube(f"https://youtu.be/{VIDEO_ID}?t=5") is None
    queue.remove_ids([item.id])
    assert queue.add_youtube(URL) is not None
    queue.clear()
    assert queue.add_youtube(URL) is not None


def test_downloader_options_and_progress(monkeypatch, tmp_path):
    import yt_dlp

    options = {}
    class FakeDownloader:
        def __init__(self, opts):
            options.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            assert url == URL and download
            hook = options["progress_hooks"][0]
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            hook({"status": "downloading", "downloaded_bytes": 50})
            hook({"status": "finished"})
            (tmp_path / "audio.webm").write_bytes(b"downloaded")
            return {"title": "Video\nTitle"}

        def prepare_filename(self, info):
            return str(tmp_path / "audio.webm")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)
    monkeypatch.setattr("audio_transcript.youtube.shutil.which", lambda name: "node.exe" if name == "node" else None)
    progress = []
    result = download_audio(URL, tmp_path, on_progress=progress.append, should_stop=lambda: False)
    assert result.title == "Video Title"
    assert result.path == tmp_path / "audio.webm"
    assert progress == [50, -1, 100]
    assert options["noplaylist"] and options["cachedir"] is False
    assert not options["remote_components"]
    assert options["skip_unavailable_fragments"] is False
    assert options["format"].split("/")[-1] == "bestaudio"
    assert "cookiesfrombrowser" not in options
    with pytest.raises(RuntimeError, match="Live and upcoming"):
        options["match_filter"]({"is_live": True})


def test_download_stop_before_network_and_missing_runtime(monkeypatch, tmp_path):
    with pytest.raises(TranscriptionCancelled):
        download_audio(URL, tmp_path, on_progress=lambda _: None, should_stop=lambda: True)
    monkeypatch.setattr("audio_transcript.youtube.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="Node.js"):
        download_audio(URL, tmp_path, on_progress=lambda _: None, should_stop=lambda: False)


@pytest.mark.parametrize("cancel", [False, True])
def test_downloader_failure_or_stop_reports_correct_boundary(monkeypatch, tmp_path, cancel):
    import yt_dlp
    from yt_dlp.utils import DownloadError

    stopped = False
    calls = []
    class BrokenDownloader:
        def __init__(self, opts):
            self.options = opts
            calls.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            nonlocal stopped
            stopped = cancel
            raise DownloadError("unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", BrokenDownloader)
    monkeypatch.setattr("audio_transcript.youtube.shutil.which", lambda _: "node.exe")
    with pytest.raises(TranscriptionCancelled if cancel else RuntimeError):
        download_audio(URL, tmp_path, on_progress=lambda _: None, should_stop=lambda: stopped)
    assert len(calls) == 1


@pytest.mark.parametrize("message,kind", [
    ("Sign in to confirm you’re not a bot", "bot_check"),
    ("Sign in to confirm you're not a bot", "bot_check"),
    ("Private video. Sign in", "access_restricted"),
    ("Sign in to confirm your age", "access_restricted"),
    ("Video unavailable", "unavailable"),
    ("Requested format is not available", "formats"),
    ("Connection timed out", "network"),
    ("HTTP Error 429: Too Many Requests", "network"),
    ("HTTP Error 403: Forbidden", "request_rejected"),
    ("No supported JavaScript runtime found", "components"),
    ("Unexpected extraction problem", "download_failed"),
])
def test_failure_classification(message, kind):
    from audio_transcript.youtube import failure_kind
    assert failure_kind(message) == kind


@pytest.mark.parametrize("second_error", [None, "Sign in to confirm you're not a bot", "Video unavailable"])
def test_one_fresh_session_retry_and_safe_diagnostics(monkeypatch, tmp_path, second_error):
    import yt_dlp
    import audio_transcript.youtube as module
    from yt_dlp.utils import DownloadError

    instances, events = [], []
    class Downloader:
        def __init__(self, options):
            self.options = options
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("closed")

        def extract_info(self, *args, **kwargs):
            logger = self.options["logger"]
            logger.debug("[youtube] Downloading player API JSON")
            for index in range(20):
                logger.warning(f"Missing PO Token https://host/?token=SECRET Cookie: SECRET{index}")
            if len(instances) == 1:
                raise DownloadError("Sign in to confirm you're not a bot https://secret/?auth=SECRET")
            if second_error:
                raise DownloadError(second_error + " Cookie: SECRET")
            (tmp_path / "audio.webm").write_bytes(b"complete")
            return {"title": "Example"}

        def prepare_filename(self, info):
            return str(tmp_path / "audio.webm")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Downloader)
    monkeypatch.setattr(module.shutil, "which", lambda _: "runtime")
    monkeypatch.setattr(module, "component_summary", lambda _: "yt-dlp: test; node: 22.0.0")
    monkeypatch.setattr(module, "wait_to_retry", lambda _: events.append("wait"))
    def run():
        return download_audio(URL, tmp_path, on_progress=lambda _: None, should_stop=lambda: False,
                              on_retry=lambda: events.append("retry"))
    if second_error:
        with pytest.raises(module.YouTubeDownloadError) as error:
            run()
        assert error.value.attempts == 2
        assert "player information" in str(error.value)
        assert "SECRET" not in str(error.value) and "https://" not in str(error.value)
        assert str(error.value).count("Some formats require a PO token") == 1
        assert len(str(error.value)) < 1500
    else:
        assert run().path.read_bytes() == b"complete"
    assert len(instances) == 2 and instances[0] is not instances[1]
    assert events == ["closed", "retry", "wait", "closed"]


def test_stop_during_retry_wait_never_opens_second_session(monkeypatch, tmp_path):
    import yt_dlp
    import audio_transcript.youtube as module
    from yt_dlp.utils import DownloadError

    instances = []
    stopped = False
    class Downloader:
        def __init__(self, options):
            instances.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, *args, **kwargs):
            raise DownloadError("Sign in to confirm you're not a bot")
    def sleep(_):
        nonlocal stopped
        stopped = True
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Downloader)
    monkeypatch.setattr(module.shutil, "which", lambda _: "runtime")
    monkeypatch.setattr(module.time, "sleep", sleep)
    with pytest.raises(TranscriptionCancelled):
        download_audio(URL, tmp_path, on_progress=lambda _: None, should_stop=lambda: stopped)
    assert len(instances) == 1


def test_retry_wait_has_a_deadline(monkeypatch):
    import audio_transcript.youtube as module
    elapsed = 0.0
    def sleep(seconds):
        nonlocal elapsed
        assert 0 < seconds <= 0.1
        elapsed += seconds
    monkeypatch.setattr(module.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(module.time, "sleep", sleep)
    module.wait_to_retry(lambda: False)
    assert elapsed == pytest.approx(10)


def test_runtime_diagnostics_only_include_version(monkeypatch):
    import audio_transcript.youtube as module
    from types import SimpleNamespace
    commands = []
    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(stdout="v22.21.1\nSECRET unexpected output", returncode=0)
    monkeypatch.setattr(module.subprocess, "run", run)
    summary = module.component_summary({"node": {"path": "C:/private/node.exe"}})
    assert "node: 22.21.1" in summary
    assert "SECRET" not in summary and "private" not in summary
    assert commands[0][0] == ["C:/private/node.exe", "--version"]
    assert commands[0][1]["timeout"] == 5
