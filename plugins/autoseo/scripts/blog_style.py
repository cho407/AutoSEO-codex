#!/usr/bin/env python3
"""Manage safe, local blog presentation profiles.

Profiles describe editorial structure and visual direction only. They do not
claim or calculate search ranking, and the selected profile never stores article
text, URLs, images, cookies or account identifiers.
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from file_safety import read_text_limited, write_text_atomically
from writing_identity import data_directory

SCHEMA_VERSION = 1
CONFIG_FILENAME = "blog-style.json"
CATALOG_FILENAME = "blog-style-profiles.json"


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / CATALOG_FILENAME


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    """Load and validate the shipped public catalog once per process."""
    value = json.loads(_catalog_path().read_text(encoding="utf-8"))
    return validate_catalog(value)


def _text(value: object, label: str, *, maximum: int = 300) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return result


def _text_list(value: object, label: str, *, maximum_items: int = 20) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError(f"{label} must be a list with at most {maximum_items} items")
    return [_text(item, f"{label} item", maximum=500) for item in value]


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unsupported {label} fields: {sorted(unknown)}")


def validate_catalog(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("blog style catalog must be an object")
    _reject_unknown(value, {"schema_version", "kind", "default_profile", "quality_floor", "profiles"}, "catalog")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != "BlogStyleCatalog":
        raise ValueError("blog style catalog must be BlogStyleCatalog v1")
    default = _text(value.get("default_profile"), "default_profile", maximum=80)
    floor = value.get("quality_floor")
    if not isinstance(floor, dict):
        raise ValueError("quality_floor must be an object")
    _reject_unknown(floor, {"purpose", "title", "article", "visual", "boundaries"}, "quality_floor")
    _text(floor.get("purpose"), "quality_floor.purpose")
    title = floor.get("title")
    if not isinstance(title, dict):
        raise ValueError("quality_floor.title must be an object")
    _reject_unknown(title, {"pattern", "rules"}, "quality_floor.title")
    _text(title.get("pattern"), "quality_floor.title.pattern")
    _text_list(title.get("rules"), "quality_floor.title.rules", maximum_items=10)
    for key in ("article", "visual", "boundaries"):
        _text_list(floor.get(key), f"quality_floor.{key}", maximum_items=20)
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("profiles must be a non-empty object")
    for name, profile in profiles.items():
        if not isinstance(name, str) or not name or len(name) > 80:
            raise ValueError("profile names must be short strings")
        if not isinstance(profile, dict):
            raise ValueError(f"profile {name} must be an object")
        required = {"label", "scope", "description", "format_preset", "image_profile", "article_sequence", "text", "visual", "keep", "avoid", "uncertain"}
        if not required <= set(profile):
            raise ValueError(f"profile {name} is missing required fields")
        _text(profile["label"], f"profiles.{name}.label", maximum=100)
        if profile["scope"] not in {"universal", "personal"}:
            raise ValueError(f"profiles.{name}.scope must be universal or personal")
        _text(profile["description"], f"profiles.{name}.description", maximum=500)
        _text(profile["format_preset"], f"profiles.{name}.format_preset", maximum=80)
        _text(profile["image_profile"], f"profiles.{name}.image_profile", maximum=80)
        for key in ("article_sequence", "keep", "avoid", "uncertain"):
            _text_list(profile[key], f"profiles.{name}.{key}", maximum_items=20)
        if not isinstance(profile["text"], dict) or not isinstance(profile["visual"], dict):
            raise ValueError(f"profiles.{name}.text and visual must be objects")
    if default not in profiles:
        raise ValueError("default_profile must name a shipped profile")
    return copy.deepcopy(value)


def profile_names() -> tuple[str, ...]:
    return tuple(sorted(catalog()["profiles"]))


def validate_profile_name(value: object) -> str:
    if not isinstance(value, str) or value not in catalog()["profiles"]:
        raise ValueError(f"unsupported blog style profile; choose one of {list(profile_names())}")
    return value


def config_path(data_dir: str | Path | None = None) -> Path:
    return data_directory(data_dir, create=False) / CONFIG_FILENAME


def _timestamp(value: object) -> str:
    text = _text(value, "confirmed_at", maximum=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("confirmed_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("confirmed_at must include a timezone")
    return text


def validate_selection(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("blog style selection must be an object")
    _reject_unknown(value, {"schema_version", "kind", "profile", "confirmed_at"}, "selection")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != "BlogStyleSelection":
        raise ValueError("blog style selection must be BlogStyleSelection v1")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "BlogStyleSelection",
        "profile": validate_profile_name(value.get("profile")),
        "confirmed_at": _timestamp(value.get("confirmed_at")),
    }


def load_selection(data_dir: str | Path | None = None) -> dict[str, Any]:
    path = config_path(data_dir)
    if path.is_symlink():
        raise ValueError("blog style selection path must not be a symbolic link")
    return validate_selection(json.loads(read_text_limited(path, extensions={".json"})))


def selected_profile_name(data_dir: str | Path | None = None) -> str:
    path = config_path(data_dir)
    if not path.exists():
        return str(catalog()["default_profile"])
    return load_selection(data_dir)["profile"]


def resolve_profile(profile: str | None = None, *, data_dir: str | Path | None = None) -> dict[str, Any]:
    name = validate_profile_name(profile) if profile is not None else selected_profile_name(data_dir)
    result = copy.deepcopy(catalog()["profiles"][name])
    result["profile"] = name
    result["quality_floor"] = copy.deepcopy(catalog()["quality_floor"])
    return result


def profile_status(data_dir: str | Path | None = None) -> dict[str, Any]:
    path = config_path(data_dir)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "configured": path.is_file() and not path.is_symlink(),
        "path": str(path),
        "default_profile": catalog()["default_profile"],
    }
    if not result["configured"]:
        result.update({"profile": catalog()["default_profile"], "valid": True})
        return result
    try:
        selection = load_selection(data_dir)
        profile = catalog()["profiles"][selection["profile"]]
        result.update({"profile": selection["profile"], "label": profile["label"], "scope": profile["scope"], "valid": True})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.update({"valid": False, "error": str(exc)})
    return result


def save_selection(
    profile: str,
    *,
    data_dir: str | Path | None = None,
    confirmed: bool,
    confirmed_at: str | None = None,
) -> Path:
    if not confirmed:
        raise ValueError("explicit confirmation is required before saving a blog style")
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "BlogStyleSelection",
        "profile": validate_profile_name(profile),
        "confirmed_at": confirmed_at or datetime.now(timezone.utc).isoformat(),
    }
    normalized = validate_selection(value)
    directory = data_directory(data_dir, create=True)
    path = directory / CONFIG_FILENAME
    if path.is_symlink():
        raise ValueError("blog style selection path must not be a symbolic link")
    write_text_atomically(path, json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", extensions={".json"})
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def reset_selection(*, data_dir: str | Path | None = None, confirmed: bool) -> bool:
    if not confirmed:
        raise ValueError("explicit confirmation is required before resetting a blog style")
    path = config_path(data_dir)
    if path.is_symlink():
        raise ValueError("blog style selection path must not be a symbolic link")
    if not path.exists():
        return False
    path.unlink()
    return True


def _public_presets() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "default_profile": catalog()["default_profile"],
        "profiles": {
            name: {"label": profile["label"], "scope": profile["scope"], "image_profile": profile["image_profile"]}
            for name, profile in catalog()["profiles"].items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("presets")
    show = sub.add_parser("show")
    show.add_argument("profile", nargs="?")
    select = sub.add_parser("set")
    select.add_argument("profile", choices=profile_names())
    select.add_argument("--confirm", action="store_true")
    reset = sub.add_parser("reset")
    reset.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result: object = profile_status(args.data_dir)
        elif args.command == "presets":
            result = _public_presets()
        elif args.command == "show":
            result = resolve_profile(args.profile, data_dir=args.data_dir)
        elif args.command == "set":
            result = {"saved": True, "profile": args.profile, "path": str(save_selection(args.profile, data_dir=args.data_dir, confirmed=args.confirm))}
        else:
            result = {"reset": reset_selection(data_dir=args.data_dir, confirmed=args.confirm)}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
