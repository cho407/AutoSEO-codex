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
def test_launcher_prefers_python_matching_managed_state(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_failing_executable(binaries / "py")
    _write_failing_executable(binaries / "python3")
    _write_python_proxy(binaries / "python", "python-3.13")
    _write_python_proxy(binaries / "python3.14", "python-3.14", pass_checks=True)
    data_dir = tmp_path / "runtime-data"
    data_dir.mkdir()
    (data_dir / "runtime-state.json").write_text(
        json.dumps({"python": "3.14"}), encoding="utf-8"
    )
    managed_bin = data_dir / ".venv" / "bin"
    managed_bin.mkdir(parents=True)
    _write_python_proxy(managed_bin / "python", "managed-python-3.14", pass_checks=True)
    result, selections = _run_launcher(tmp_path, binaries, data_dir)

    assert result.returncode == 3
    assert selections == ["managed-python-3.14"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_launcher_uses_matching_versioned_python_when_managed_python_is_missing(
    tmp_path: Path,
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_failing_executable(binaries / "py")
    _write_failing_executable(binaries / "python3")
    _write_python_proxy(binaries / "python", "python-3.13")
    _write_python_proxy(binaries / "python3.14", "python-3.14", pass_checks=True)
    data_dir = tmp_path / "runtime-data"
    data_dir.mkdir()
    (data_dir / "runtime-state.json").write_text(
        json.dumps({"python": "3.14"}), encoding="utf-8"
    )

    result, selections = _run_launcher(tmp_path, binaries, data_dir)

    assert result.returncode == 3
    assert selections == ["python-3.14"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_launcher_explicit_python_override_has_absolute_priority(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_failing_executable(binaries / "py")
    _write_failing_executable(binaries / "python3")
    _write_python_proxy(binaries / "python", "python-3.13")
    _write_python_proxy(binaries / "python3.14", "python-3.14", pass_checks=True)
    override = binaries / "explicit-python"
    _write_python_proxy(override, "explicit-override")
    data_dir = tmp_path / "runtime-data"
    data_dir.mkdir()
    (data_dir / "runtime-state.json").write_text(
        json.dumps({"python": "3.14"}), encoding="utf-8"
    )

    result, selections = _run_launcher(
        tmp_path, binaries, data_dir, override=override
    )

    assert result.returncode == 3
    assert selections == ["explicit-override"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_launcher_falls_back_to_generic_python_without_state(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_failing_executable(binaries / "py")
    _write_failing_executable(binaries / "python3")
    _write_python_proxy(binaries / "python", "python-3.13")
    data_dir = tmp_path / "runtime-data"

    result, selections = _run_launcher(tmp_path, binaries, data_dir)

    assert result.returncode == 3
    assert selections == ["python-3.13"]
    assert not data_dir.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_launcher_rejects_invalid_explicit_python_override(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    invalid_override = binaries / "invalid-python"
    _write_failing_executable(invalid_override)

    result, selections = _run_launcher(
        tmp_path, binaries, tmp_path / "runtime-data", override=invalid_override
    )

    assert result.returncode == 2
    assert "AUTOSEO_PYTHON is not a usable" in result.stderr
    assert selections == []


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"python": "3.14"}, "3.14"),
        ({"python": "3.9"}, None),
        ({"python": "03.14"}, None),
        ({"python": "3.14; python"}, None),
        ({"python": "3." + "9" * 5_000}, None),
        ({"python": [3, 14]}, None),
        ([], None),
    ],
)
def test_state_python_version_accepts_only_canonical_supported_values(
    tmp_path: Path, state: object, expected: str | None
) -> None:
    runtime = _load_runtime()
    (tmp_path / "runtime-state.json").write_text(json.dumps(state), encoding="utf-8")

    assert runtime._state_python_version(tmp_path) == expected


def _write_failing_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    path.chmod(0o755)


def _write_python_proxy(path: Path, label: str, *, pass_checks: bool = False) -> None:
    check_action = "exit 0" if pass_checks else 'exec "$AUTOSEO_TEST_REAL_PYTHON" "$@"'
    path.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "-c" ]; then\n'
        f"    {check_action}\n"
        "fi\n"
        'case "${2:-}" in\n'
        '    --launcher-state-*) exec "$AUTOSEO_TEST_REAL_PYTHON" "$@" ;;\n'
        "esac\n"
        f"printf '%s\\n' '{label}' >> \"$AUTOSEO_TEST_SELECTION_LOG\"\n"
        'exec "$AUTOSEO_TEST_REAL_PYTHON" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_launcher(
    tmp_path: Path,
    binaries: Path,
    data_dir: Path,
    *,
    override: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    selection_log = tmp_path / "selected-python.log"
    env = os.environ.copy()
    env["PATH"] = str(binaries) + os.pathsep + os.defpath
    env["AUTOSEO_DATA_DIR"] = str(data_dir)
    env["AUTOSEO_TEST_REAL_PYTHON"] = sys.executable
    env["AUTOSEO_TEST_SELECTION_LOG"] = str(selection_log)
    if override is None:
        env.pop("AUTOSEO_PYTHON", None)
    else:
        env["AUTOSEO_PYTHON"] = str(override)
    result = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "autoseo"), "doctor", "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    selections = (
        selection_log.read_text(encoding="utf-8").splitlines()
        if selection_log.exists()
        else []
    )
    return result, selections


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
