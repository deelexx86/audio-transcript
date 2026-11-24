"""Install the optional CUDA runtime locally or provision a Windows SSH host."""
from __future__ import annotations

import argparse
import base64
import io
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-cuda.txt"


def worker_archive() -> bytes:
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("__main__.py", "from audio_transcript.remote_worker import main\nmain()\n")
        for module in (
            "__init__", "acceleration", "bootstrap_models", "paths", "profiles",
            "remote_gpu", "remote_worker", "transcription",
        ):
            path = Path("audio_transcript") / f"{module}.py"
            package.write(ROOT / "src" / path, path.as_posix())
    return archive.getvalue()


def provision_remote(alias: str) -> None:
    from audio_transcript.remote_gpu import REMOTE_COMMAND, ssh_command

    ssh = ssh_command(alias)
    requirements = [
        line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    packages = ", ".join("'" + line.replace("'", "''") + "'" for line in requirements)
    script = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Join-Path $env:LOCALAPPDATA 'AudioTranscriptGpu'
New-Item -Path $root -ItemType Directory -Force | Out-Null
$staged = Join-Path $root ([Guid]::NewGuid().ToString() + '.tmp')
$backup = "$staged.old"
try {
    $archive = [IO.File]::Open($staged, 'CreateNew')
    try { [Console]::OpenStandardInput().CopyTo($archive) } finally { $archive.Dispose() }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        py -3.11 -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Python 3.11 environment.' }
    }
    $packages = @(__PACKAGES__)
    & $python -m pip --disable-pip-version-check install @packages
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the CUDA runtime.' }
    $worker = Join-Path $root 'worker.pyz'
    if ([IO.File]::Exists($worker)) { [IO.File]::Replace($staged, $worker, $backup) }
    else { [IO.File]::Move($staged, $worker) }
} finally {
    if ([IO.File]::Exists($staged)) { [IO.File]::Delete($staged) }
    if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
}
""".replace("__PACKAGES__", packages)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        [*ssh, f"powershell.exe -NoProfile -NonInteractive -EncodedCommand {encoded}"],
        input=worker_archive(), check=True,
    )
    subprocess.run([*ssh, f"{REMOTE_COMMAND} --bootstrap"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", metavar="SSH_ALIAS", help="Provision a Windows OpenSSH host")
    args = parser.parse_args()
    try:
        if args.remote is not None:
            provision_remote(args.remote)
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=True)
            from audio_transcript.acceleration import prepare_cuda
            prepare_cuda()
            print("CUDA device 0 supports float16.")
    except subprocess.CalledProcessError as exc:
        parser.exit(1, f"GPU setup command exited with status {exc.returncode}. See the diagnostics above.\n")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"GPU setup failed: {exc}\n")


if __name__ == "__main__":
    main()
