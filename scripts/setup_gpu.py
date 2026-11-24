"""Install the optional CUDA runtime locally or provision a Windows SSH host."""
from __future__ import annotations

import argparse
import base64
import io
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

AUDIOCPP_ASSETS = {
    "bin": "05e3f7ac7753992e57caeeb223af45669a85e4cd56a539f16453cdb3e78ef494",
    "cudart": "79cb17e005b0f614b2938dc3294c98e80ee9aafd696492ccefb0247faef4aac2",
}
ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-cuda.txt"


def worker_archive() -> bytes:
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("__main__.py", "from audio_transcript.remote_worker import main\nmain()\n")
        for module in (
            "__init__", "acceleration", "bootstrap_models", "paths", "profiles",
            "remote_gpu", "remote_worker", "transcription", "model_catalog",
            "model_storage", "model_service", "gguf_asr",
        ):
            path = Path("audio_transcript") / f"{module}.py"
            package.write(ROOT / "src" / path, path.as_posix())
    return archive.getvalue()


def provision_remote(alias: str, *, worker_only: bool = False) -> None:
    from audio_transcript.model_storage import RUNTIME_DIRECTORY
    from audio_transcript.remote_gpu import ssh_command

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
$zip = "$staged.zip"
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
    if (__PROVISION_RUNTIME__) {
        $runtime = Join-Path $root '__RUNTIME__'
        if (-not ((Test-Path (Join-Path $runtime 'audiocpp_cli.exe')) -and
                   (Test-Path (Join-Path $runtime 'cublas64_13.dll')))) {
            $version = '__RUNTIME__'.Substring('audio.cpp-'.Length)
            $assets = @{__ASSETS__}
            foreach ($kind in 'bin', 'cudart') {
                $package = "audio-$version-$kind-windows-x64-cuda13.3.zip"
                & curl.exe --fail --retry 3 -LsS "https://github.com/0xShug0/audio.cpp/releases/download/$version/$package" -o $zip
                if ($LASTEXITCODE -ne 0) { throw "Could not download $package" }
                if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $assets[$kind]) {
                    throw "Checksum did not match for $package"
                }
                Expand-Archive -LiteralPath $zip -DestinationPath $runtime -Force
                [IO.File]::Delete($zip)
            }
        }
        & (Join-Path $runtime 'audiocpp_cli.exe') --version
        if ($LASTEXITCODE -ne 0) { throw 'audio.cpp could not start.' }
    }
    $worker = Join-Path $root 'worker-v2.pyz'
    if ([IO.File]::Exists($worker)) { [IO.File]::Replace($staged, $worker, $backup) }
    else { [IO.File]::Move($staged, $worker) }
} finally {
    if ([IO.File]::Exists($staged)) { [IO.File]::Delete($staged) }
    if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
    if ([IO.File]::Exists($zip)) { [IO.File]::Delete($zip) }
}
""".replace("__PACKAGES__", packages)
    script = script.replace("__PROVISION_RUNTIME__", "$false" if worker_only else "$true")
    script = script.replace("__RUNTIME__", RUNTIME_DIRECTORY).replace(
        "__ASSETS__", "; ".join(f"{key} = '{digest}'" for key, digest in AUDIOCPP_ASSETS.items()),
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        [*ssh, f"powershell.exe -NoProfile -NonInteractive -EncodedCommand {encoded}"],
        input=worker_archive(), check=True,
    )



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", metavar="SSH_ALIAS", help="Provision a Windows OpenSSH host")
    parser.add_argument("--worker-only", action="store_true", help="Update the remote worker without installing audio.cpp")
    args = parser.parse_args()
    if args.worker_only and not args.remote:
        parser.error("--worker-only requires --remote")
    try:
        if args.remote is not None:
            provision_remote(args.remote, worker_only=args.worker_only)
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
