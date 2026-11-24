"""Manage only catalog-owned files, under a lock shared with inference."""
from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from urllib.parse import quote
from urllib.request import Request, urlopen

from filelock import FileLock, Timeout

from audio_transcript.model_catalog import CatalogModel


REMOTE_MODELS = Path(r"D:\models\audio-transcript")
RUNTIME_DIRECTORY = "audio.cpp-v0.9.6"


def plain_path(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"Model storage cannot use a link or junction: {path}")


def model_path(root: Path, model: CatalogModel) -> Path:
    directory = root / model.directory_name
    for path in (root.parent, root, directory):
        plain_path(path)
    return directory


@contextmanager
def model_lock(root: Path, model: CatalogModel):
    directory = model_path(root, model)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / f".{model.directory_name}.lock"
    plain_path(lock_path)
    try:
        with FileLock(lock_path, timeout=0):
            yield directory
    except Timeout as exc:
        raise RuntimeError("This model is in use by another operation.") from exc


def installed_bytes(root: Path, model: CatalogModel) -> int | None:
    directory = model_path(root, model)
    total = 0
    for entry in model.files:
        target = directory / entry.name
        plain_path(target)
        if not target.is_file() or target.stat().st_size != entry.size:
            return None
        total += entry.size
    return total


def has_managed_files(root: Path, model: CatalogModel) -> bool:
    directory = model_path(root, model)
    return any((directory / (entry.name + suffix)).is_file()
               for entry in model.files for suffix in ("", ".partial"))


def download(root: Path, model: CatalogModel, progress) -> None:
    with model_lock(root, model) as directory:
        directory.mkdir(exist_ok=True)
        total = sum(entry.size for entry in model.files)
        completed = 0
        for entry in model.files:
            target = directory / entry.name
            partial = target.with_name(target.name + ".partial")
            plain_path(target)
            plain_path(partial)
            if target.exists():
                if not target.is_file() or target.stat().st_size != entry.size:
                    raise RuntimeError(f"Remove the incomplete model before replacing {entry.name}.")
            else:
                url = f"https://huggingface.co/{model.repository}/resolve/{model.revision}/{quote(entry.path)}"
                receive_file(url, partial, entry.size, entry.sha256, lambda count: progress(completed + count, total))
                os.replace(partial, target)
            completed += entry.size
            progress(completed, total)


def receive_file(url: str, target: Path, size: int, digest: str, progress) -> None:
    offset = target.stat().st_size if target.exists() else 0
    if offset > size:
        target.unlink()
        offset = 0
    if offset < size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            if offset and response.status == 206:
                if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise RuntimeError("The checkpoint server returned an unexpected byte range.")
                mode = "ab"
            else:
                offset = 0
                mode = "wb"
            last_update = monotonic()
            with target.open(mode) as output:
                while block := response.read(1024 * 1024):
                    offset += len(block)
                    if offset > size:
                        raise RuntimeError("The checkpoint exceeded its published size.")
                    output.write(block)
                    if monotonic() - last_update >= 0.25:
                        progress(offset)
                        last_update = monotonic()
    if offset != size:
        raise RuntimeError("The checkpoint download is incomplete. Retry to resume.")
    if digest:
        with target.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != digest:
            target.unlink()
            raise RuntimeError("The checkpoint checksum did not match. Retry to download it again.")


def remove(root: Path, model: CatalogModel) -> None:
    with model_lock(root, model) as directory:
        targets = [directory / (item.name + suffix) for item in model.files for suffix in ("", ".partial")]
        for target in targets:
            plain_path(target)
            if target.exists() and not target.is_file():
                raise ValueError(f"Unexpected directory at model file path: {target}")
        for target in targets:
            target.unlink(missing_ok=True)
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
