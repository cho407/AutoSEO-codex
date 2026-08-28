#!/usr/bin/env python3
"""Run the test suite from files committed to the current Git revision."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise ValueError(f"unsafe path in git archive: {member.name}")
    return members


def main() -> int:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="autoseo-git-archive-") as directory:
        destination = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            members = _safe_members(archive)
            if sys.version_info >= (3, 12):
                archive.extractall(destination, members=members, filter="data")
            else:
                archive.extractall(destination, members=members)
        completed = subprocess.run(
            [sys.executable, "-m", "pytest"],
            cwd=destination,
            check=False,
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
