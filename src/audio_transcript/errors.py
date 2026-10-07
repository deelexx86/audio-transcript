from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessingFailure:
    """Language-independent failure data, rendered by the UI at display time."""

    source: str
    details: str
    kind: str = "transcription"
