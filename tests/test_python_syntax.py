from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_python_files_compile(tmp_path: Path) -> None:
    python_files = sorted((ROOT / "plugins" / "autoseo" / "scripts").glob("*.py"))
    python_files.append(ROOT / "scripts" / "build_release.py")
    for index, source in enumerate(python_files):
        destination = tmp_path / f"{index}.pyc"
        py_compile.compile(str(source), cfile=str(destination), doraise=True)
