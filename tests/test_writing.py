from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from content_humanize import humanize  # noqa: E402
from writing_identity import (  # noqa: E402
    TONE_PRESETS,
    intake_questions,
    load_profile,
    profile_status,
    save_profile,
    validate_profile,
)


def _profile() -> dict:
    return {
        "schema_version": 1,
        "kind": "WritingIdentity",
        "profile_name": "기본 블로그",
        "identity": {
            "role": "직접 사용해 본 도구를 설명하는 실무자",
            "expertise": ["콘텐츠 운영"],
            "experience_claims": ["직접 사용한 기능만 경험으로 표현"],
        },
        "audience": {
            "primary": "처음 자동화를 접하는 1인 운영자",
            "knowledge_level": "beginner",
            "needs": ["쉽고 검증 가능한 설명"],
        },
        "voice": {
            "preset": "friendly",
            "sentence_ending": "haeyo",
            "warmth": 4,
            "directness": 4,
            "humor": 1,
            "emoji": "none",
            "custom_instructions": "과장 없이 짧게 설명한다.",
        },
        "lexicon": {
            "preferred_terms": ["준비도"],
            "avoid_terms": ["무조건", "완벽한"],
        },
        "content_defaults": {
            "goal": "독자가 기능을 이해하고 직접 판단하게 돕기",
            "cta_style": "soft",
            "market": "KR",
            "language": "ko",
            "platforms": ["naver", "tistory"],
        },
        "confirmed_at": "2026-08-31T00:00:00+00:00",
    }


def test_writing_identity_is_versioned_and_tone_presets_are_explicit() -> None:
    validated = validate_profile(_profile())

    assert validated["schema_version"] == 1
    assert validated["kind"] == "WritingIdentity"
    assert validated["voice"]["preset"] == "friendly"
    assert {"friendly", "professional", "expert-friendly", "custom"} <= set(
        TONE_PRESETS
    )


def test_shipped_writing_identity_example_matches_runtime_contract() -> None:
    example = json.loads(
        (ROOT / "plugins" / "autoseo" / "examples" / "writing-identity-v1.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (ROOT / "plugins" / "autoseo" / "schema" / "writing-identity.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert validate_profile(example)["kind"] == "WritingIdentity"
    assert schema["properties"]["schema_version"]["const"] == 1


def test_first_run_intake_only_asks_for_missing_identity_context() -> None:
    questions = intake_questions(
        {
            "identity": {"role": "현장 경험을 공유하는 운영자"},
            "audience": {"primary": "초보 블로거"},
        }
    )

    assert {item["id"] for item in questions} == {"goal", "voice"}
    assert all(item["question"].endswith("?") for item in questions)


def test_profile_store_requires_confirmation_and_uses_owner_only_permissions(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "autoseo-data"

    with pytest.raises(ValueError, match="confirmation"):
        save_profile(_profile(), data_dir=data_dir, confirmed=False)

    path = save_profile(_profile(), data_dir=data_dir, confirmed=True)
    assert path.name == "writing-identity.json"
    assert load_profile(data_dir=data_dir) == _profile()
    assert profile_status(data_dir=data_dir)["configured"] is True
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_profile_store_rejects_symlink_destination(tmp_path: Path) -> None:
    data_dir = tmp_path / "autoseo-data"
    data_dir.mkdir()
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    (data_dir / "writing-identity.json").symlink_to(target)

    with pytest.raises(ValueError, match="symbolic link"):
        save_profile(_profile(), data_dir=data_dir, confirmed=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {}


def test_profile_rejects_unlisted_nested_content_and_symlink_data_directory(
    tmp_path: Path,
) -> None:
    profile = _profile()
    profile["identity"]["draft"] = "글 본문은 프로필에 저장하면 안 됩니다."
    with pytest.raises(ValueError, match="identity fields"):
        validate_profile(profile)

    real_data = tmp_path / "real-autoseo-data"
    real_data.mkdir()
    linked_data = tmp_path / "linked-autoseo-data"
    linked_data.symlink_to(real_data, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        save_profile(_profile(), data_dir=linked_data, confirmed=True)


def test_korean_polish_removes_safe_translationese_without_changing_facts() -> None:
    source = (
        "2026년 기준으로 설정을 하는 것이 가능합니다. "
        "확인을 하겠습니다. 자세한 내용은 https://example.com/a?x=1 에 있습니다."
    )

    result = humanize(source, language="ko", tone="professional")

    assert "설정할 수 있습니다" in result["cleaned"]
    assert "확인하겠습니다" in result["cleaned"]
    assert "2026년" in result["cleaned"]
    assert "https://example.com/a?x=1" in result["cleaned"]
    assert result["language"] == "ko"
    assert result["change_count"] >= 2
    assert result["tone_validation"]["requested"] == "professional"


def test_korean_polish_flags_ambiguous_calques_instead_of_guessing() -> None:
    source = "이 부분에 있어서 결과는 여러 조건에 의해 달라집니다."

    result = humanize(source, language="ko", tone="friendly")

    assert result["cleaned"] == source
    labels = {item["label"] for item in result["translationese_findings"]}
    assert {"에-있어서", "에-의해"} <= labels
    assert result["tone_validation"]["compliant"] is False
