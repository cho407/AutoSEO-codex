from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_submission_cases_cover_positive_and_negative_behavior() -> None:
    cases = json.loads((ROOT / "submission" / "test-cases.json").read_text())
    assert cases["schemaVersion"] == 1
    assert cases["plugin"] == "autoseo"
    assert len(cases["positive"]) >= 5
    assert len(cases["negative"]) >= 3
    all_cases = cases["positive"] + cases["negative"]
    assert len({case["id"] for case in all_cases}) == len(all_cases)
    for case in all_cases:
        assert case["prompt"].strip()
        assert len(case["expectedBehavior"]) >= 2


def test_repository_contains_no_likely_committed_secret() -> None:
    patterns = (
        re.compile(r"ghp_[A-Za-z0-9]{36,}"),
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )
    ignored = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "build", "dist"}
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or any(part in ignored or part.endswith(".egg-info") for part in path.parts)
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in patterns:
            assert not pattern.search(text), path


def test_release_archive_is_deterministic_and_self_contained() -> None:
    command = [sys.executable, str(ROOT / "scripts" / "build_release.py")]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    archive_path = Path(first.stdout.strip())
    first_bytes = archive_path.read_bytes()
    subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    assert archive_path.read_bytes() == first_bytes
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "autoseo/.codex-plugin/plugin.json" in names
    assert "autoseo/LICENSE" in names
    assert "autoseo/README.md" in names
    assert "autoseo/skills/autoseo/SKILL.md" in names
    assert all(name.startswith("autoseo/") for name in names)
