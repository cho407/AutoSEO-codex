#!/usr/bin/env python3
"""Validate and privately store the user's confirmed writing identity."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from file_safety import read_text_limited, write_text_atomically

SCHEMA_VERSION = 1
PROFILE_FILENAME = "writing-identity.json"

TONE_PRESETS: dict[str, dict[str, Any]] = {
    "friendly": {
        "label": "친근한 설명형",
        "sentence_ending": "haeyo",
        "guidance": "쉬운 말과 해요체를 쓰되 가볍거나 과장되게 말하지 않습니다.",
    },
    "professional": {
        "label": "전문적인 보고형",
        "sentence_ending": "hamnida",
        "guidance": "합니다체로 핵심과 근거를 단정하게 설명합니다.",
    },
    "expert-friendly": {
        "label": "전문가의 쉬운 설명",
        "sentence_ending": "haeyo",
        "guidance": "전문 용어를 풀어 쓰고 판단 근거와 한계를 함께 밝힙니다.",
    },
    "conversational": {
        "label": "자연스러운 대화형",
        "sentence_ending": "haeyo",
        "guidance": "실제 대화처럼 쓰되 유행어, 감탄사, 수사 질문을 남발하지 않습니다.",
    },
    "warm": {
        "label": "따뜻한 공감형",
        "sentence_ending": "haeyo",
        "guidance": "독자의 상황을 먼저 헤아리고 부담 없는 다음 행동을 제안합니다.",
    },
    "concise": {
        "label": "짧고 단정한 실무형",
        "sentence_ending": "hamnida",
        "guidance": "한 문장에 한 가지 정보만 두고 중복과 서론을 줄입니다.",
    },
    "persuasive": {
        "label": "근거 중심 설득형",
        "sentence_ending": "haeyo",
        "guidance": "효과를 단정하지 않고 근거, 조건, 다음 행동 순으로 설득합니다.",
    },
    "custom": {
        "label": "사용자 지정",
        "sentence_ending": "custom",
        "guidance": "확인된 사용자 지침을 우선하되 사실과 출처는 바꾸지 않습니다.",
    },
}

_TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "profile_name",
    "identity",
    "audience",
    "voice",
    "lexicon",
    "content_defaults",
    "confirmed_at",
}
_KNOWLEDGE_LEVELS = {"beginner", "intermediate", "advanced", "mixed"}
_SENTENCE_ENDINGS = {"haeyo", "hamnida", "mixed-intentional", "custom"}
_EMOJI_LEVELS = {"none", "light", "moderate"}
_CTA_STYLES = {"none", "soft", "direct"}
_PLATFORMS = {"web", "naver", "tistory", "newsletter", "social", "other"}


def _default_data_dir() -> Path:
    configured = os.environ.get("AUTOSEO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "autoseo").resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (base / "autoseo").resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / "autoseo").resolve()


def _data_directory(data_dir: str | os.PathLike[str] | None, *, create: bool) -> Path:
    raw_path = Path(data_dir) if data_dir is not None else _default_data_dir()
    raw_path = raw_path.expanduser()
    if raw_path.is_symlink():
        raise ValueError("writing identity data path must not be a symbolic link")
    path = raw_path.resolve(strict=False)
    broad = {Path(path.anchor).resolve()}
    try:
        broad.add(Path.home().resolve())
    except RuntimeError:
        pass
    if path in broad:
        raise ValueError("writing identity must use a dedicated data directory")
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("writing identity data path must be a regular directory")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def profile_path(data_dir: str | os.PathLike[str] | None = None) -> Path:
    return _data_directory(data_dir, create=False) / PROFILE_FILENAME


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unsupported {label} fields: {sorted(unknown)}")


def _text(value: object, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return cleaned


def _optional_text(value: object, label: str, *, maximum: int = 500) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return cleaned


def _text_list(value: object, label: str, *, maximum_items: int = 30) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError(f"{label} must be a list with at most {maximum_items} items")
    return [_text(item, f"{label} item", maximum=120) for item in value]


def _bounded_int(value: object, label: str, *, minimum: int = 0, maximum: int = 5) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label, maximum=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return text


def validate_profile(profile: object) -> dict[str, Any]:
    """Return a normalized copy of WritingIdentity v1 or raise ``ValueError``."""
    data = copy.deepcopy(_mapping(profile, "profile"))
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(f"unsupported profile fields: {sorted(unknown)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version must be 1")
    if data.get("kind") != "WritingIdentity":
        raise ValueError("kind must be WritingIdentity")

    data["profile_name"] = _text(data.get("profile_name"), "profile_name", maximum=80)
    identity = _mapping(data.get("identity"), "identity")
    _reject_unknown(identity, {"role", "expertise", "experience_claims"}, "identity")
    identity["role"] = _text(identity.get("role"), "identity.role", maximum=240)
    identity["expertise"] = _text_list(identity.get("expertise", []), "identity.expertise")
    identity["experience_claims"] = _text_list(
        identity.get("experience_claims", []), "identity.experience_claims"
    )

    audience = _mapping(data.get("audience"), "audience")
    _reject_unknown(audience, {"primary", "knowledge_level", "needs"}, "audience")
    audience["primary"] = _text(audience.get("primary"), "audience.primary", maximum=240)
    if audience.get("knowledge_level") not in _KNOWLEDGE_LEVELS:
        raise ValueError(f"audience.knowledge_level must be one of {sorted(_KNOWLEDGE_LEVELS)}")
    audience["needs"] = _text_list(audience.get("needs", []), "audience.needs")

    voice = _mapping(data.get("voice"), "voice")
    _reject_unknown(
        voice,
        {
            "preset",
            "sentence_ending",
            "warmth",
            "directness",
            "humor",
            "emoji",
            "custom_instructions",
        },
        "voice",
    )
    preset = voice.get("preset")
    if preset not in TONE_PRESETS:
        raise ValueError(f"voice.preset must be one of {sorted(TONE_PRESETS)}")
    ending = voice.get("sentence_ending")
    if ending not in _SENTENCE_ENDINGS:
        raise ValueError(f"voice.sentence_ending must be one of {sorted(_SENTENCE_ENDINGS)}")
    voice["warmth"] = _bounded_int(voice.get("warmth"), "voice.warmth")
    voice["directness"] = _bounded_int(voice.get("directness"), "voice.directness")
    voice["humor"] = _bounded_int(voice.get("humor"), "voice.humor")
    if voice.get("emoji") not in _EMOJI_LEVELS:
        raise ValueError(f"voice.emoji must be one of {sorted(_EMOJI_LEVELS)}")
    voice["custom_instructions"] = _optional_text(
        voice.get("custom_instructions", ""), "voice.custom_instructions"
    )
    if preset == "custom" and not voice["custom_instructions"]:
        raise ValueError("custom voice requires voice.custom_instructions")

    lexicon = _mapping(data.get("lexicon", {}), "lexicon")
    _reject_unknown(lexicon, {"preferred_terms", "avoid_terms"}, "lexicon")
    lexicon["preferred_terms"] = _text_list(
        lexicon.get("preferred_terms", []), "lexicon.preferred_terms"
    )
    lexicon["avoid_terms"] = _text_list(
        lexicon.get("avoid_terms", []), "lexicon.avoid_terms"
    )

    defaults = _mapping(data.get("content_defaults"), "content_defaults")
    _reject_unknown(
        defaults,
        {"goal", "cta_style", "market", "language", "platforms"},
        "content_defaults",
    )
    defaults["goal"] = _text(defaults.get("goal"), "content_defaults.goal", maximum=300)
    if defaults.get("cta_style") not in _CTA_STYLES:
        raise ValueError(f"content_defaults.cta_style must be one of {sorted(_CTA_STYLES)}")
    defaults["market"] = _text(defaults.get("market"), "content_defaults.market", maximum=20)
    defaults["language"] = _text(
        defaults.get("language"), "content_defaults.language", maximum=20
    )
    platforms = defaults.get("platforms")
    if not isinstance(platforms, list) or not platforms or len(platforms) > 6:
        raise ValueError("content_defaults.platforms must contain between 1 and 6 items")
    if any(not isinstance(item, str) or item not in _PLATFORMS for item in platforms):
        raise ValueError(f"content_defaults.platforms must use {sorted(_PLATFORMS)}")
    defaults["platforms"] = list(dict.fromkeys(platforms))
    data["confirmed_at"] = _timestamp(data.get("confirmed_at"), "confirmed_at")
    return data


def intake_questions(context: object | None = None) -> list[dict[str, str]]:
    """Return only the short first-run questions not answered by known context."""
    value = context if isinstance(context, dict) else {}
    identity = value.get("identity") if isinstance(value.get("identity"), dict) else {}
    audience = value.get("audience") if isinstance(value.get("audience"), dict) else {}
    voice = value.get("voice") if isinstance(value.get("voice"), dict) else {}
    defaults = (
        value.get("content_defaults")
        if isinstance(value.get("content_defaults"), dict)
        else {}
    )
    questions: list[dict[str, str]] = []
    if not identity.get("role"):
        questions.append(
            {
                "id": "identity",
                "question": "누가 어떤 경험이나 전문성을 바탕으로 쓰는 글인가요?",
                "why": "확인되지 않은 1인칭 경험이나 권위를 만들어 내지 않기 위해 필요합니다.",
            }
        )
    if not audience.get("primary"):
        questions.append(
            {
                "id": "audience",
                "question": "가장 먼저 읽어야 할 독자는 누구이고 무엇이 어려운가요?",
                "why": "설명 깊이와 용어 난이도를 정하는 기준입니다.",
            }
        )
    if not defaults.get("goal"):
        questions.append(
            {
                "id": "goal",
                "question": "독자가 글을 읽은 뒤 무엇을 이해하거나 행동하면 좋을까요?",
                "why": "글의 결론과 CTA를 자연스럽게 맞추기 위해 필요합니다.",
            }
        )
    if not voice.get("preset"):
        questions.append(
            {
                "id": "voice",
                "question": "친근한 설명형, 전문가의 쉬운 설명, 전문적인 보고형 중 어느 말투가 가장 가깝나요?",
                "why": "문장 종결과 정보 전달 방식을 일관되게 유지하는 기준입니다.",
            }
        )
    return questions


def profile_status(data_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    path = profile_path(data_dir)
    configured = path.is_file() and not path.is_symlink()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "configured": configured,
        "path": str(path),
    }
    if configured:
        try:
            profile = load_profile(data_dir)
            result.update(
                {
                    "profile_name": profile["profile_name"],
                    "tone": profile["voice"]["preset"],
                    "valid": True,
                }
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result.update({"valid": False, "error": str(exc)})
    return result


def load_profile(data_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    path = profile_path(data_dir)
    if path.is_symlink():
        raise ValueError("writing identity path must not be a symbolic link")
    value = json.loads(read_text_limited(path, extensions={".json"}))
    return validate_profile(value)


def save_profile(
    profile: object,
    *,
    data_dir: str | os.PathLike[str] | None = None,
    confirmed: bool,
) -> Path:
    if not confirmed:
        raise ValueError("explicit confirmation is required before saving a writing identity")
    value = validate_profile(profile)
    directory = _data_directory(data_dir, create=True)
    path = directory / PROFILE_FILENAME
    if path.is_symlink():
        raise ValueError("writing identity path must not be a symbolic link")
    write_text_atomically(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        extensions={".json"},
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def reset_profile(
    *, data_dir: str | os.PathLike[str] | None = None, confirmed: bool
) -> bool:
    if not confirmed:
        raise ValueError("explicit confirmation is required before resetting a writing identity")
    path = profile_path(data_dir)
    if path.is_symlink():
        raise ValueError("writing identity path must not be a symbolic link")
    if not path.exists():
        return False
    path.unlink()
    return True


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    return _mapping(value, "JSON input")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("show")
    sub.add_parser("tones")
    questions = sub.add_parser("questions")
    questions.add_argument("--context")
    validate = sub.add_parser("validate")
    validate.add_argument("input")
    save = sub.add_parser("save")
    save.add_argument("input")
    save.add_argument("--confirm", action="store_true")
    reset = sub.add_parser("reset")
    reset.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            result: object = profile_status(args.data_dir)
        elif args.command == "show":
            result = load_profile(args.data_dir)
        elif args.command == "tones":
            result = {"schema_version": 1, "tones": TONE_PRESETS}
        elif args.command == "questions":
            context = _load_json(args.context) if args.context else {}
            result = {"schema_version": 1, "questions": intake_questions(context)}
        elif args.command == "validate":
            result = {"valid": True, "profile": validate_profile(_load_json(args.input))}
        elif args.command == "save":
            path = save_profile(
                _load_json(args.input), data_dir=args.data_dir, confirmed=args.confirm
            )
            result = {"saved": True, "path": str(path)}
        else:
            result = {
                "reset": reset_profile(data_dir=args.data_dir, confirmed=args.confirm)
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
