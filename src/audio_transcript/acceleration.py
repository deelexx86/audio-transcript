from __future__ import annotations

import os
import re
from enum import StrEnum
from functools import cache
from importlib.metadata import PackageNotFoundError, distribution


class ExecutionMode(StrEnum):
    CPU = "cpu"
    LOCAL_CUDA = "local_cuda"
    REMOTE_CUDA = "remote_cuda"


class CudaUnavailable(RuntimeError):
    pass


def valid_ssh_alias(alias: object) -> bool:
    return isinstance(alias, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}", alias) is not None


@cache
def _register_windows_dlls() -> tuple:
    wheel = distribution("nvidia-cublas-cu12")
    directories = sorted({
        wheel.locate_file(file).resolve().parent
        for file in wheel.files or () if file.suffix.lower() == ".dll"
    })
    if not directories:
        raise CudaUnavailable("No cuBLAS DLLs found. Reinstall requirements-cuda.txt.")
    # Retain the handles for the lifetime of this application process.
    # Native CUDA components can also call LoadLibrary using PATH.
    handles = tuple(os.add_dll_directory(str(directory)) for directory in directories)
    os.environ["PATH"] = os.pathsep.join([*map(str, directories), os.environ.get("PATH", "")])
    return handles


@cache
def prepare_cuda() -> None:
    import ctranslate2

    try:
        if not ctranslate2.get_cuda_device_count():
            raise CudaUnavailable("CTranslate2 found no CUDA device. Check the NVIDIA GPU and driver.")
        if os.name == "nt":
            _register_windows_dlls()
        if "float16" not in ctranslate2.get_supported_compute_types("cuda", 0):
            raise CudaUnavailable("CUDA device 0 does not support the required float16 compute type.")
    except PackageNotFoundError as exc:
        raise CudaUnavailable("Install requirements-cuda.txt in the Audio Transcript environment.") from exc
    except CudaUnavailable:
        raise
    except (RuntimeError, OSError) as exc:
        raise CudaUnavailable(str(exc)) from exc
