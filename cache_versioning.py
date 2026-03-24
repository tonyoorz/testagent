#!/usr/bin/env python3
"""
Shared cache version helpers.

Builds a stable dataset fingerprint from key source files so cache keys can
invalidate automatically when data changes.
"""

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List


DEFAULT_FINGERPRINT_PATTERNS = [
    "database/local_data.db",
    "database/local_data_rebuilt.db",
    "defect/*_defect.json",
    "defect/*_defect_master.json",
    "aida/*.xlsx",
    "history/*_history.json",
]


def _collect_existing_files(project_root: Path, patterns: Iterable[str], max_files: int) -> List[Path]:
    files: List[Path] = []
    for pattern in patterns:
        matches = sorted(project_root.glob(pattern))
        for path in matches:
            if path.is_file():
                files.append(path)
                if len(files) >= max_files:
                    return files
    return files


def _file_signature(path: Path) -> str:
    try:
        stat = path.stat()
        rel = path.as_posix()
        return f"{rel}|{int(stat.st_mtime_ns)}|{int(stat.st_size)}"
    except OSError:
        return f"{path.as_posix()}|missing"


@lru_cache(maxsize=32)
def dataset_fingerprint(project_root: str = ".", extra_tag: str = "", max_files: int = 2000) -> str:
    root = Path(project_root).resolve()
    signatures: List[str] = []

    for item in _collect_existing_files(root, tuple(DEFAULT_FINGERPRINT_PATTERNS), max_files=max_files):
        signatures.append(_file_signature(item.relative_to(root)))

    if not signatures:
        signatures.append("no-data-files")

    payload = "\n".join(signatures)
    if extra_tag:
        payload += f"\nextra:{extra_tag}"

    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def get_cache_version(prefix: str = "v5", project_root: str = ".", extra_tag: str = "") -> str:
    digest = dataset_fingerprint(project_root=project_root, extra_tag=extra_tag)
    return f"{prefix}_{digest[:12]}"


def clear_fingerprint_cache() -> None:
    dataset_fingerprint.cache_clear()


if __name__ == "__main__":
    code_tag = os.environ.get("APP_CACHE_CODE_VERSION", "")
    print(get_cache_version(prefix="v5", extra_tag=code_tag))