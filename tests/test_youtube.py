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
    class BrokenDownloader:
        def __init__(self, opts):
            self.options = opts

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
