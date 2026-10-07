from __future__ import annotations

from pathlib import Path

import av
import pytest

from audio_transcript.queueing import QueueManager
from audio_transcript.audio import (
    AudioDecodeError,
    format_duration,
    is_supported_media,
    probe_duration,
    scan_folder,
)


def test_supported_formats_and_non_recursive_scan(tmp_path: Path) -> None:
    names = [
        "voice.OGG", "song.mp3", "memo.m4a", "clip.wav", "telegram.webm", "phone.AMR",
        "video.MP4", "movie.m4v", "meeting.mkv", "camera.mov", "legacy.avi", "clip.wmv",
        "clip.asf", "clip.flv", "clip.mpg", "clip.mpeg", "clip.ts", "clip.mts", "clip.m2ts",
        "clip.vob", "clip.ogv", "phone.3gp", "phone.3g2",
    ]
    for name in names:
        (tmp_path / name).touch()
    (tmp_path / "notes.txt").touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.ogg").touch()
    (nested / "hidden.mp4").touch()

    assert all(is_supported_media(name) for name in names)
    assert not is_supported_media("notes.txt")
    assert {path.name for path in scan_folder(tmp_path)} == set(names)


def test_duration_formatting() -> None:
    assert format_duration(None) == "—"
    assert format_duration(163) == "02:43"
    assert format_duration(3723) == "1:02:03"


def test_pyav_decodes_ogg_opus(tmp_path: Path) -> None:
    target = tmp_path / "голосовое.ogg"
    container = av.open(str(target), mode="w", format="ogg")
    stream = container.add_stream("libopus", rate=48_000)
    stream.layout = "mono"
    frame = av.AudioFrame(format="s16", layout="mono", samples=4_800)
    frame.sample_rate = 48_000
    frame.planes[0].update(bytes(frame.planes[0].buffer_size))
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()

    duration = probe_duration(target, decode_first_frame=True)
    assert duration is not None
    assert duration > 0


def test_corrupt_audio_has_actionable_error(tmp_path: Path) -> None:
    corrupt = tmp_path / "broken.ogg"
    corrupt.write_bytes(b"not an ogg file")
    try:
        probe_duration(corrupt, decode_first_frame=True)
    except AudioDecodeError as exc:
        assert "Could not decode audio file" in str(exc)
    else:
        raise AssertionError("corrupt audio unexpectedly decoded")


@pytest.mark.parametrize("header,frame_size,sample_rate", [(b"#!AMR\n", 13, 8000), (b"#!AMR-WB\n", 18, 16000)])
def test_amr_decodes_through_pyav_and_whisper(tmp_path, header, frame_size, sample_rate):
    from faster_whisper.audio import decode_audio

    source = tmp_path / "запись.AMR"
    # Storage-format mode-0 speech frames with zero payload; no binary fixture required.
    source.write_bytes(header + (b"\x04" + bytes(frame_size - 1)) * 50)
    assert probe_duration(source, decode_first_frame=True) == pytest.approx(1.0)
    with av.open(str(source)) as container:
        frames = list(container.decode(audio=0))
    assert sum(frame.samples for frame in frames) == sample_rate
    decoded = decode_audio(str(source), sampling_rate=16000)
    assert len(decoded) == 16000


def test_corrupt_amr_is_reported(tmp_path):
    source = tmp_path / "broken.amr"
    source.write_bytes(b"not audio")
    with pytest.raises(AudioDecodeError, match="Could not decode"):
        probe_duration(source, decode_first_frame=True)


def write_test_video(target, container_format, video_codec, audio_codec=None):
    from fractions import Fraction

    with av.open(str(target), mode="w", format=container_format) as container:
        video = container.add_stream(video_codec, rate=25)
        video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
        audio = container.add_stream(audio_codec, rate=48_000) if audio_codec else None
        if audio:
            audio.layout = "mono"
            audio.bit_rate = 128_000
        for index in range(25):
            frame = av.VideoFrame(64, 64, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            frame.pts, frame.time_base = index, Fraction(1, 25)
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
        if audio:
            frame = av.AudioFrame(format="s16", layout="mono", samples=48_000)
            frame.sample_rate, frame.pts, frame.time_base = 48_000, 0, Fraction(1, 48_000)
            frame.planes[0].update(bytes(frame.planes[0].buffer_size))
            for packet in audio.encode(frame):
                container.mux(packet)
            for packet in audio.encode(None):
                container.mux(packet)


@pytest.mark.parametrize("extension,container_format,video_codec,audio_codec", [
    ("mp4", "mp4", "mpeg4", "aac"),
    ("mov", "mov", "mpeg4", "aac"),
    ("mkv", "matroska", "mpeg4", "aac"),
    ("avi", "avi", "mpeg4", "pcm_s16le"),
    ("webm", "webm", "libvpx", "libopus"),
    ("wmv", "asf", "wmv2", "wmav2"),
    ("flv", "flv", "flv", "libmp3lame"),
    ("mpeg", "mpeg", "mpeg2video", "mp2"),
    ("ts", "mpegts", "mpeg2video", "mp2"),
    ("3gp", "3gp", "mpeg4", "aac"),
])
def test_video_audio_decodes_through_pyav_and_whisper(
    tmp_path, extension, container_format, video_codec, audio_codec,
):
    from faster_whisper.audio import decode_audio

    source = tmp_path / f"Встреча.{extension.upper()}"
    write_test_video(source, container_format, video_codec, audio_codec)
    original = source.read_bytes()
    with av.open(str(source)) as container:
        assert len(container.streams.video) == 1
        assert len(container.streams.audio) == 1
    assert probe_duration(source, decode_first_frame=True) > 0
    decoded = decode_audio(str(source), sampling_rate=16000)
    assert 14_000 <= len(decoded) <= 20_000
    queue = QueueManager()
    assert len(queue.add_paths([source]).added) == 1
    assert queue.add_paths([source]).duplicates == 1
    assert source.read_bytes() == original


def test_silent_video_fails_before_model_loading_and_batch_continues(monkeypatch, tmp_path):
    from audio_transcript.profiles import FAST
    from audio_transcript.worker import BatchWorker, WorkItem

    source = tmp_path / "silent.mp4"
    write_test_video(source, "mp4", "mpeg4")
    corrupt = tmp_path / "broken.mkv"
    corrupt.write_bytes(b"invalid video")
    with pytest.raises(AudioDecodeError, match="no audio stream"):
        probe_duration(source, decode_first_frame=True)
    with pytest.raises(AudioDecodeError, match="Could not decode"):
        probe_duration(corrupt, decode_first_frame=True)
    monkeypatch.setattr("audio_transcript.worker.LocalTranscriber", lambda _: pytest.fail("Must not load model"))
    worker = BatchWorker([
        WorkItem("silent", source, "", None), WorkItem("corrupt", corrupt, "", None),
    ], FAST, "workspace")
    failures, finished = [], []
    worker.item_failed.connect(lambda item_id, message: failures.append((item_id, message)))
    worker.finished.connect(finished.append)
    worker.run()
    assert [item_id for item_id, _ in failures] == ["silent", "corrupt"]
    assert "no audio stream" in failures[0][1]
    assert finished == [False]
    assert source.exists() and corrupt.read_bytes() == b"invalid video"
