from __future__ import annotations

from datetime import datetime
from pathlib import Path

from audio_transcript.artifacts import output_parent, render_markdown, write_artifacts


PROCESSED = datetime(2026, 8, 31, 17, 10)


def test_workspace_artifacts_and_collision_are_append_safe(tmp_path: Path) -> None:
    source = tmp_path / "исходники" / "Переговоры.ogg"
    source.parent.mkdir()
    source.write_bytes(b"untouched source")
    workspace = tmp_path / "transcripts"

    first = write_artifacts(
        source=source,
        transcript="  Добрый день.\n",
        processed_at=PROCESSED,
        duration=163,
        language="ru",
        speaker="Евгений",
        model_name="whisper-large-v3",
        output_mode="workspace",
        workspace=workspace,
    )
    second = write_artifacts(
        source=source,
        transcript="Повторная версия.",
        processed_at=PROCESSED,
        duration=163,
        language="ru",
        speaker="",
        model_name="whisper-large-v3-turbo",
        output_mode="workspace",
        workspace=workspace,
    )

    assert first.directory == workspace / "2026" / "2026-08-31" / "Переговоры"
    assert second.directory.name == "Переговоры_2"
    assert first.text_path.read_text(encoding="utf-8") == "Добрый день.\n"
    markdown = first.markdown_path.read_text(encoding="utf-8")
    assert "Source: Переговоры.ogg" in markdown
    assert "Processed: 2026-08-31 17:10" in markdown
    assert "Duration: 02:43" in markdown
    assert "Language: ru" in markdown
    assert "Speaker: Евгений" in markdown
    assert "Model: whisper-large-v3" in markdown
    assert str(source.parent) not in markdown
    assert source.read_bytes() == b"untouched source"


def test_same_source_folder_mode_groups_outputs(tmp_path: Path) -> None:
    source = tmp_path / "meeting.m4a"
    source.touch()
    parent, name = output_parent(source, "source", PROCESSED)
    assert parent == tmp_path
    assert name == "meeting_transcript"


def test_markdown_omits_blank_optional_metadata() -> None:
    markdown = render_markdown(
        source_name="voice.ogg",
        processed_at=PROCESSED,
        duration=None,
        language=None,
        speaker="  ",
        model_name="whisper-large-v3",
        transcript="Text",
    )
    assert "Language:" not in markdown
    assert "Speaker:" not in markdown
    assert markdown.endswith("Text\n")
