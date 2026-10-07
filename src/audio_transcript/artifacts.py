from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from audio_transcript.audio import format_duration
from audio_transcript.paths import TRANSCRIPTS_DIR


INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    directory: Path
    text_path: Path
    markdown_path: Path


def safe_source_stem(source: str | Path) -> str:
    stem = INVALID_FOLDER_CHARS.sub("_", Path(source).stem).strip(" .")
    return stem or "transcript"


def output_parent(
    source: str | Path,
    output_mode: str,
    processed_at: datetime,
    workspace: str | Path = TRANSCRIPTS_DIR,
) -> tuple[Path, str]:
    source_path = Path(source)
    stem = safe_source_stem(source_path)
    if output_mode == "source":
        return source_path.parent, f"{stem}_transcript"
    if output_mode != "workspace":
        raise ValueError(f"Unknown output mode: {output_mode}")
    return Path(workspace) / processed_at.strftime("%Y") / processed_at.strftime("%Y-%m-%d"), stem


def reserve_output_directory(parent: str | Path, base_name: str) -> Path:
    parent_path = Path(parent)
    parent_path.mkdir(parents=True, exist_ok=True)
    candidate = parent_path / base_name
    suffix = 1
    while True:
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            suffix += 1
            candidate = parent_path / f"{base_name}_{suffix}"


def render_markdown(
    *,
    source_name: str,
    processed_at: datetime,
    duration: float | None,
    language: str | None,
    speaker: str,
    model_name: str,
    transcript: str,
    source_url: str | None = None,
    source_title: str = "",
) -> str:
    clean_speaker = " ".join(speaker.split())
    lines = [
        "# Transcript",
        "",
        f"Source: {'YouTube' if source_url else Path(source_name).name}",
        f"Processed: {processed_at.strftime('%Y-%m-%d %H:%M')}",
        f"Duration: {format_duration(duration)}",
    ]
    if language:
        lines.append(f"Language: {' '.join(language.split())}")
    if source_url:
        lines.append(f"URL: {source_url}")
        lines.append(f"Title: {' '.join(source_title.split())}")
    if clean_speaker:
        lines.append(f"Speaker: {clean_speaker}")
    lines.extend(
        [
            f"Model: {model_name}",
            "",
            "## Transcript",
            "",
            transcript.strip(),
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(
    *,
    source: str | Path,
    transcript: str,
    processed_at: datetime,
    duration: float | None,
    language: str | None,
    speaker: str,
    model_name: str,
    output_mode: str,
    workspace: str | Path = TRANSCRIPTS_DIR,
    source_url: str | None = None,
    source_title: str = "",
) -> ArtifactResult:
    clean_transcript = transcript.strip()
    parent, base_name = output_parent(source, output_mode, processed_at, workspace)
    directory = reserve_output_directory(parent, base_name)
    text_path = directory / "transcript.txt"
    markdown_path = directory / "transcript.md"
    text_temporary = directory / "transcript.txt.tmp"
    markdown_temporary = directory / "transcript.md.tmp"
    try:
        text_temporary.write_text(clean_transcript + "\n", encoding="utf-8")
        markdown_temporary.write_text(
            render_markdown(
                source_name=Path(source).name,
                processed_at=processed_at,
                duration=duration,
                language=language,
                speaker=speaker,
                model_name=model_name,
                transcript=clean_transcript,
                source_url=source_url,
                source_title=source_title,
            ),
            encoding="utf-8",
        )
        os.replace(text_temporary, text_path)
        os.replace(markdown_temporary, markdown_path)
        return ArtifactResult(directory, text_path, markdown_path)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
