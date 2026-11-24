from __future__ import annotations

import argparse
from pathlib import Path

from faster_whisper.utils import download_model

from audio_transcript.paths import MODELS_DIR, ensure_runtime_directories
from audio_transcript.profiles import PROFILES, PROFILES_BY_KEY, model_is_ready


def bootstrap(profile_keys: list[str] | None = None, *, models_dir: Path | None = None) -> int:
    if models_dir is None:
        ensure_runtime_directories()
    selected = PROFILES if not profile_keys else tuple(PROFILES_BY_KEY[key] for key in profile_keys)
    for profile in selected:
        path = models_dir / profile.directory_name if models_dir is not None else profile.path
        if model_is_ready(profile, models_dir=models_dir):
            print(f"Ready: {profile.display_name}\n  {path}")
            continue
        path.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {profile.display_name} into:\n  {path}")
        download_model(profile.download_name, output_dir=str(path))
        if not model_is_ready(profile, models_dir=models_dir):
            raise RuntimeError(f"Download completed but the model is incomplete: {path}")
        print(f"Ready: {profile.display_name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Audio Transcript models into the repository-local models directory."
    )
    parser.add_argument(
        "profiles",
        nargs="*",
        metavar="PROFILE",
        help="Optional profile(s); defaults to both accuracy and fast.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    unknown = sorted(set(args.profiles) - set(PROFILES_BY_KEY))
    if unknown:
        parser.error(
            f"unknown profile(s): {', '.join(unknown)}; choose from: "
            f"{', '.join(sorted(PROFILES_BY_KEY))}"
        )
    try:
        return bootstrap(args.profiles)
    except Exception as exc:
        print(f"Model bootstrap failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
