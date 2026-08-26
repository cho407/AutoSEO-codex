#!/usr/bin/env python3
"""Build a deterministic, reviewable AutoSEO plugin archive."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "autoseo"
DIST_ROOT = REPOSITORY_ROOT / "dist"
MANIFEST = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
EXCLUDED_PARTS = {".DS_Store", "__pycache__", ".pytest_cache"}
MAX_FILE_BYTES = 10 * 1024 * 1024
ARCHIVE_TIME = (2026, 1, 1, 0, 0, 0)


def release_files() -> list[Path]:
    files: list[Path] = []
    for path in PLUGIN_ROOT.rglob("*"):
        relative = path.relative_to(PLUGIN_ROOT)
        if any(part in EXCLUDED_PARTS or part.endswith(".pyc") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"release archive cannot contain a symlink: {relative}")
        if path.is_file():
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"release file exceeds 10 MiB: {relative}")
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def build() -> Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("name") != "autoseo":
        raise ValueError("plugin manifest name must be autoseo")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("plugin manifest version is missing")

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    destination = DIST_ROOT / f"autoseo-{version}.zip"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".autoseo-", suffix=".zip", dir=DIST_ROOT)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source in release_files():
                relative = source.relative_to(PLUGIN_ROOT)
                info = zipfile.ZipInfo(f"autoseo/{relative.as_posix()}", ARCHIVE_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if relative.as_posix() == "scripts/autoseo" else 0o644
                info.external_attr = (mode & 0xFFFF) << 16
                archive.writestr(info, source.read_bytes())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    print(build())
