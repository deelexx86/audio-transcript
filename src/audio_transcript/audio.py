from __future__ import annotations

from pathlib import Path

import av


SUPPORTED_EXTENSIONS = frozenset({
    ".ogg", ".mp3", ".m4a", ".wav", ".webm", ".amr",
    ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".asf", ".flv",
    ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob", ".ogv", ".3gp", ".3g2",
})


class AudioDecodeError(RuntimeError):
    pass


def is_supported_media(path: str | Path) -> bool:
    return Path(path).suffix.casefold() in SUPPORTED_EXTENSIONS


def scan_folder(folder: str | Path) -> list[Path]:
    directory = Path(folder)
    if not directory.is_dir():
        return []
    return sorted(
        (entry for entry in directory.iterdir() if entry.is_file() and is_supported_media(entry)),
        key=lambda path: path.name.casefold(),
    )


def probe_duration(path: str | Path, *, decode_first_frame: bool = False) -> float | None:
    source = Path(path)
    try:
        with av.open(str(source), mode="r") as container:
            audio_streams = [stream for stream in container.streams if stream.type == "audio"]
            if not audio_streams:
                raise AudioDecodeError("The file contains no audio stream.")
            stream = audio_streams[0]
            duration: float | None = None
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = float(container.duration / av.time_base)

            if decode_first_frame:
                try:
                    next(container.decode(stream))
                except StopIteration as exc:
                    raise AudioDecodeError("The audio stream contains no decodable frames.") from exc
            return duration if duration is None or duration >= 0 else None
    except AudioDecodeError:
        raise
    except (av.error.FFmpegError, OSError, ValueError) as exc:
        raise AudioDecodeError(f"Could not decode audio file: {exc}") from exc


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
