"""Local file storage with path-traversal protection.

Layout::

    data/uploads/<candidate_id>/original.<ext>   (original document)
    data/tmp/<candidate_id>/...                   (transient processing files)

File names on disk never derive from user input.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from app.config import get_settings

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class StorageError(Exception):
    pass


def _check_id(candidate_id: str) -> None:
    if not _UUID_RE.match(candidate_id):
        raise StorageError("invalid candidate id")


def _inside(base: Path, p: Path) -> Path:
    base_r, p_r = base.resolve(), p.resolve()
    if base_r != p_r and base_r not in p_r.parents:
        raise StorageError("path escapes storage directory")
    return p_r


def candidate_upload_dir(candidate_id: str) -> Path:
    _check_id(candidate_id)
    base = get_settings().uploads_dir
    return _inside(base, base / candidate_id)


def candidate_tmp_dir(candidate_id: str) -> Path:
    _check_id(candidate_id)
    base = get_settings().tmp_dir
    return _inside(base, base / candidate_id)


def save_original(candidate_id: str, file_type: str, content: bytes) -> str:
    """Write atomically (temp file in the same directory, then rename)."""
    if file_type not in {"pdf", "docx", "txt", "jpg", "png"}:
        raise StorageError("invalid file type")
    d = candidate_upload_dir(candidate_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"original.{file_type}"
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".upload-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.replace(tmp, d / name)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return name


def original_path(candidate_id: str, stored_filename: str) -> Path:
    d = candidate_upload_dir(candidate_id)
    return _inside(d, d / stored_filename)


def read_original(candidate_id: str, stored_filename: str) -> bytes:
    return original_path(candidate_id, stored_filename).read_bytes()


def remove_candidate_files(candidate_id: str) -> dict[str, object]:
    """Delete upload + temp directories. Returns what was removed/failed."""
    removed: list[str] = []
    failed: list[str] = []
    for kind, d in (("uploads", candidate_upload_dir(candidate_id)), ("tmp", candidate_tmp_dir(candidate_id))):
        if not d.exists():
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        for f in files:
            try:
                _overwrite_and_unlink(f)
                removed.append(f"{kind}/{f.name}")
            except OSError:
                failed.append(f"{kind}/{f.name}")
        shutil.rmtree(d, ignore_errors=True)
        if d.exists():
            failed.append(f"{kind}/")
    return {"removed": removed, "failed": failed}


def _overwrite_and_unlink(path: Path) -> None:
    """Best-effort overwrite before unlink. On SSDs (wear levelling) and
    copy-on-write / journaling filesystems this does NOT guarantee that the
    physical blocks are erased – see docs/known-limitations.md."""
    try:
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            remaining = size
            chunk = b"\x00" * 65536
            while remaining > 0:
                n = min(remaining, len(chunk))
                fh.write(chunk[:n])
                remaining -= n
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    path.unlink()


def candidate_files_exist(candidate_id: str) -> list[str]:
    left = []
    for d in (candidate_upload_dir(candidate_id), candidate_tmp_dir(candidate_id)):
        if d.exists():
            left.append(str(d.relative_to(get_settings().data_dir)))
    return left
