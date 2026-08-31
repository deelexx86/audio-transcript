from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from audio_transcript.paths import MODELS_DIR


@dataclass(frozen=True, slots=True)
class ModelProfile:
    key: str
    display_name: str
    download_name: str
    artifact_name: str
    directory_name: str

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.directory_name


ACCURACY = ModelProfile(
    key="accuracy",
    display_name="Accuracy — Whisper large-v3",
    download_name="large-v3",
    artifact_name="whisper-large-v3",
    directory_name="whisper-large-v3",
)
FAST = ModelProfile(
    key="fast",
    display_name="Fast — Whisper large-v3-turbo",
    download_name="large-v3-turbo",
    artifact_name="whisper-large-v3-turbo",
    directory_name="whisper-large-v3-turbo",
)

PROFILES = (ACCURACY, FAST)
PROFILES_BY_KEY = {profile.key: profile for profile in PROFILES}


class ModelMissingError(RuntimeError):
    pass


def model_is_ready(profile: ModelProfile) -> bool:
    required = ("config.json", "model.bin", "tokenizer.json")
    return profile.path.is_dir() and all((profile.path / name).is_file() for name in required)


def require_local_model(profile: ModelProfile) -> Path:
    if not model_is_ready(profile):
        raise ModelMissingError(
            f"The {profile.display_name} model is not installed.\n\n"
            "Run bootstrap_models.bat while online, then try again.\n\n"
            f"Expected local model:\n{profile.path}"
        )
    return profile.path
