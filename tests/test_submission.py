from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

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
    assert "autoseo/skills/autoseo-audit/SKILL.md" in names
    assert "autoseo/skills/autoseo-aeo/SKILL.md" in names
    assert "autoseo/skills/autoseo-llmo/SKILL.md" in names
    assert "autoseo/skills/autoseo-neo/SKILL.md" in names
    assert "autoseo/skills/autoseo-writing/SKILL.md" in names
    assert "autoseo/skills/autoseo-naver-editor/SKILL.md" in names
    assert "autoseo/skills/autoseo-naver-editor/references/feature-compatibility.md" in names
    assert "autoseo/skills/autoseo-naver-editor/references/smarteditor-one-structure.md" in names
    assert "autoseo/skills/autoseo-tistory-editor/SKILL.md" in names
    assert "autoseo/skills/autoseo-tistory-editor/references/feature-compatibility.md" in names
    assert "autoseo/schema/evidence-bundle.schema.json" in names
    assert "autoseo/schema/lane-report.schema.json" in names
    assert "autoseo/schema/naver-document.schema.json" in names
    assert "autoseo/schema/tistory-document.schema.json" in names
    assert "autoseo/schema/writing-identity.schema.json" in names
    assert "autoseo/schema/optimization-report.schema.json" in names
    assert "autoseo/schema/trend-evidence.schema.json" in names
    assert "autoseo/data/naver-editor-features.json" in names
    assert "autoseo/data/tistory-editor-features.json" in names
    assert "autoseo/examples/naver-document-v1.json" in names
    assert "autoseo/examples/tistory-document-v1.json" in names
    assert "autoseo/examples/writing-identity-v1.json" in names
    assert "autoseo/examples/trend-evidence-v1.json" in names
    assert "autoseo/requirements-image.txt" in names
    assert "autoseo/data/feature-parity.json" in names
    assert "autoseo/data/free-sources.json" in names
    assert "autoseo/data/workflow-playbooks.json" in names
    assert "autoseo/scripts/backlink_history.py" in names
    assert "autoseo/scripts/benchmark_evidence.py" in names
    assert "autoseo/scripts/free_source_policy.py" in names
    assert "autoseo/scripts/rdap_lookup.py" in names
    assert "autoseo/scripts/search_evidence.py" in names
    assert "autoseo/scripts/trend_evidence.py" in names
    assert "autoseo/scripts/optimization_report.py" in names
    assert "autoseo/scripts/writing_identity.py" in names
    assert "autoseo/scripts/naver_document.py" in names
    assert "autoseo/scripts/naver_editor.py" in names
    assert "autoseo/scripts/privacy_mosaic.py" in names
    assert "autoseo/scripts/tistory_document.py" in names
    assert "autoseo/scripts/tistory_editor.py" in names
    assert "autoseo/scripts/workflow_catalog.py" in names
    for removed in (
        "autoseo/scripts/dataforseo_costs.py",
        "autoseo/scripts/dataforseo_merchant.py",
        "autoseo/scripts/dataforseo_normalize.py",
        "autoseo/scripts/keyword_planner.py",
        "autoseo/scripts/moz_api.py",
        "autoseo/scripts/nlp_analyze.py",
    ):
        assert removed not in names
    assert all(name.startswith("autoseo/") for name in names)


def test_every_release_file_is_tracked_by_git() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("git metadata is intentionally absent from a git archive")
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "plugins/autoseo"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    tracked_paths = {
        (ROOT / value.decode("utf-8")).resolve() for value in tracked if value
    }
    from scripts.build_release import release_files

    missing = [
        path.relative_to(ROOT).as_posix()
        for path in release_files()
        if path.resolve() not in tracked_paths
    ]
    assert missing == []


def test_sensitive_editor_runtime_artifacts_are_not_tracked_or_released() -> None:
    forbidden_parts = {
        "naver-editor-profile",
        "naver-editor-checkpoints",
        "naver-editor-diagnostics",
        "tistory-editor-profile",
        "tistory-editor-checkpoints",
        "tistory-editor-diagnostics",
        "privacy-images",
    }
    forbidden_names = {
        "naver-editor-compatibility.json",
        "tistory-editor-compatibility.json",
    }
    release_relatives = {
        path.relative_to(ROOT / "plugins" / "autoseo")
        for path in (ROOT / "plugins" / "autoseo").rglob("*")
        if path.is_file()
    }
    assert not any(forbidden_parts & set(path.parts) for path in release_relatives)
    assert not any(path.name in forbidden_names for path in release_relatives)

    if not (ROOT / ".git").exists():
        return
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    tracked_paths = [Path(value.decode("utf-8")) for value in tracked if value]
    assert not any(forbidden_parts & set(path.parts) for path in tracked_paths)
    assert not any(path.name in forbidden_names for path in tracked_paths)
