from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SCRIPTS = PLUGIN / "scripts"
RUNTIME_PATH = SCRIPTS / "runtime.py"


def _load_runtime():
    spec = importlib.util.spec_from_file_location("autoseo_runtime", RUNTIME_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_allowlist_matches_bundled_python_helpers() -> None:
    runtime = _load_runtime()
    bundled = {path.name for path in SCRIPTS.glob("*.py")} - {"runtime.py"}
    assert runtime.ALLOWED_CORE_SCRIPTS == bundled


def test_runtime_rejects_unknown_and_traversal_scripts() -> None:
    runtime = _load_runtime()
    assert runtime._resolve_script(PLUGIN, "fetch_page.py") == SCRIPTS / "fetch_page.py"
    for value in ("runtime.py", "../fetch_page.py", "/tmp/example.py", "unknown.py"):
        with pytest.raises(ValueError):
            runtime._resolve_script(PLUGIN, value)


def test_doctor_is_read_only_and_machine_readable(tmp_path: Path) -> None:
    data_dir = tmp_path / "autoseo-data"
    env = os.environ.copy()
    env["AUTOSEO_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [sys.executable, str(RUNTIME_PATH), "doctor", "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["mode"] == "override"
    assert not data_dir.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
@pytest.mark.parametrize("invalid_override", [False, True])
def test_launcher_finds_versioned_python_without_ignoring_an_explicit_override(
    tmp_path: Path, invalid_override: bool,
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("py", "python", "python3", "python3.14"):
        executable = binaries / name
        executable.write_text("#!/bin/sh\nexit 1\n")
        executable.chmod(0o755)
    (binaries / "python3.13").symlink_to(sys.executable)
    data_dir = tmp_path / "runtime-data"
    env = os.environ.copy()
    env["PATH"] = str(binaries) + os.pathsep + os.defpath
    env["AUTOSEO_DATA_DIR"] = str(data_dir)
    env.pop("AUTOSEO_PYTHON", None)
    if invalid_override:
        env["AUTOSEO_PYTHON"] = str(binaries / "python3")
    result = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "autoseo"), "doctor", "--json"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    if invalid_override:
        assert result.returncode == 2
        assert "AUTOSEO_PYTHON is not a usable" in result.stderr
    else:
        assert result.returncode == 3
        assert json.loads(result.stdout)["python_version"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert not data_dir.exists()


def test_unlighthouse_never_auto_downloads_packages() -> None:
    text = (SCRIPTS / "unlighthouse_run.py").read_text(encoding="utf-8")
    for forbidden in ("npx", "npm install", "--yes", "--package"):
        assert forbidden not in text
    assert "AUTOSEO_UNLIGHTHOUSE_BIN" in text


def test_runtime_dependency_profiles_are_explicit_and_composable() -> None:
    runtime = _load_runtime()

    assert [path.name for path in runtime._requirement_files(PLUGIN, "lite", ())] == [
        "requirements-core.txt"
    ]
    assert [
        path.name for path in runtime._requirement_files(PLUGIN, "standard", ())
    ] == ["requirements-core.txt", "requirements-browser.txt"]
    assert [
        path.name
        for path in runtime._requirement_files(PLUGIN, "lite", ("google", "report"))
    ] == [
        "requirements-core.txt",
        "requirements-google.txt",
        "requirements-report.txt",
    ]
    assert [
        path.name
        for path in runtime._requirement_files(PLUGIN, "standard", ("image",))
    ] == [
        "requirements-core.txt",
        "requirements-browser.txt",
        "requirements-image.txt",
    ]

    with pytest.raises(ValueError):
        runtime._requirement_files(PLUGIN, "unknown", ())
