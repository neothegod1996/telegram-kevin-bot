"""Resource-bounded archive extraction for optional Notion backups.

ZIP and RAR are never automatically extracted by default (see
NOTION_EXTRACT_ARCHIVES).  Explicit opt-in is still bounded to prevent archive
traversal, excessive file counts, and oversized extracted contents.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

import rarfile

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 100
DEFAULT_MAX_TOTAL_SIZE = 500 * 1024 * 1024


class ArchiveHandlerError(Exception):
    pass


class ExtractedFile:
    def __init__(self, path: str, relative_path: str, size: int):
        self.path = path
        self.relative_path = relative_path
        self.size = size
        self.name = os.path.basename(path)


def is_archive(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in (".zip", ".rar")


def _relative_path(raw: str) -> Path:
    # Telegram archives come from untrusted users.  Normalize both slash types.
    fixed = raw.replace("\\", "/")
    posix = PurePosixPath(fixed)
    if (
        posix.is_absolute()
        or not fixed
        or any(x in ("", ".", "..") for x in fixed.split("/"))
        or ":" in fixed
        or "\x00" in fixed
    ):
        raise ArchiveHandlerError(f"Unsafe archive member: {raw!r}")
    return Path(*posix.parts)


def _extract_stream(stream, target: Path, remaining: int) -> int:
    # Do not trust ZIP/RAR headers alone; also check actual decompressed bytes.
    written = 0
    with open(target, "xb") as out:
        while True:
            chunk = stream.read(min(1024 * 1024, remaining - written + 1))
            if not chunk:
                break
            written += len(chunk)
            if written > remaining:
                raise ArchiveHandlerError("Archive extraction exceeded size limit")
            out.write(chunk)
    return written


def extract_archive(
    archive_path: str,
    extract_to: Optional[str] = None,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_size: int = DEFAULT_MAX_TOTAL_SIZE,
) -> list[ExtractedFile]:
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(archive_path)
    if max_files < 1 or max_total_size < 1:
        raise ValueError("Archive limits must be positive")
    owns_dir = extract_to is None
    destination = Path(extract_to or tempfile.mkdtemp(prefix="archive_extract_"))
    destination.mkdir(parents=True, exist_ok=True)
    result: list[ExtractedFile] = []

    def validated(infos, isdir, size, filename):
        files = [x for x in infos if not isdir(x)]
        if len(files) > max_files:
            raise ArchiveHandlerError(f"Too many files: {len(files)} > {max_files}")
        total = sum(int(size(x)) for x in files)
        if total > max_total_size:
            raise ArchiveHandlerError(f"Uncompressed archive exceeds {max_total_size} bytes")
        for info in files:
            rel = _relative_path(filename(info))
            yield info, rel

    try:
        ext = Path(archive_path).suffix.lower()
        if ext == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                infos = list(validated(archive.infolist(), lambda f: f.is_dir(),
                                       lambda f: f.file_size, lambda f: f.filename))
                remaining = max_total_size
                for info, rel in infos:
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise ArchiveHandlerError("ZIP symlink not allowed")
                    target = destination / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as stream:
                        actual = _extract_stream(stream, target, remaining)
                    remaining -= actual
                    result.append(ExtractedFile(str(target), str(rel), actual))
        elif ext == ".rar":
            with rarfile.RarFile(archive_path) as archive:
                infos = list(validated(archive.infolist(), lambda f: f.isdir(),
                                       lambda f: f.file_size, lambda f: f.filename))
                remaining = max_total_size
                for info, rel in infos:
                    link_attr = getattr(info, "is_symlink", False)
                    if bool(link_attr() if callable(link_attr) else link_attr):
                        raise ArchiveHandlerError("RAR symlink not allowed")
                    target = destination / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as stream:
                        actual = _extract_stream(stream, target, remaining)
                    remaining -= actual
                    result.append(ExtractedFile(str(target), str(rel), actual))
        else:
            raise ArchiveHandlerError(f"Unsupported archive: {ext}")
        return result
    except Exception as exc:
        if owns_dir:
            shutil.rmtree(destination, ignore_errors=True)
        if isinstance(exc, ArchiveHandlerError):
            raise
        raise ArchiveHandlerError(f"Archive extraction failed: {exc}") from exc


def cleanup_extracted_files(extract_dir: str):
    if extract_dir and os.path.isdir(extract_dir):
        shutil.rmtree(extract_dir, ignore_errors=True)
