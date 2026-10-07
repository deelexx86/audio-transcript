"""Refresh Qt Linguist sources (--update) and compile bundled runtime catalogs."""
import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Extract new/changed UI text first")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    catalogs = sorted((root / "src/audio_transcript/translations").glob("app_*.ts"))
    suffix = ".exe" if sys.platform == "win32" else ""
    tools = Path(sys.executable).parent
    if args.update:
        subprocess.run([
            str(tools / f"pyside6-lupdate{suffix}"), str(root / "src/audio_transcript/ui.py"),
            "-tr-function-alias", "tr+=_status", "-locations", "none", "-source-language", "en",
            "-ts", *map(str, catalogs),
        ], check=True)
    subprocess.run([
        str(tools / f"pyside6-lrelease{suffix}"), "-nounfinished", *map(str, catalogs)
    ], check=True)


if __name__ == "__main__":
    main()
