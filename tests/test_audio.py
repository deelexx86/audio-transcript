from __future__ import annotations

from pathlib import Path

import av

from audio_transcript.audio import (
    AudioDecodeError,
    format_duration,
    is_supported_audio,
    probe_duration,
    scan_folder,
)


def test_supported_formats_and_non_recursive_scan(tmp_path: Path) -> None:
    names = ["voice.OGG", "song.mp3", "memo.m4a", "clip.wav", "telegram.webm"]
    for name in names:
        (tmp_path / name).touch()
    (tmp_path / "notes.txt").touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.ogg").touch()

    assert all(is_supported_audio(name) for name in names)
    assert not is_supported_audio("notes.txt")
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
