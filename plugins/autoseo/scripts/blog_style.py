#!/usr/bin/env python3
"""Manage safe, local blog presentation profiles.

Profiles describe editorial structure and visual direction only. They do not
claim or calculate search ranking, and the selected profile never stores article
text, URLs, images, cookies or account identifiers.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from file_safety import read_text_limited, write_text_atomically
from writing_identity import data_directory

SCHEMA_VERSION = 1
CONFIG_FILENAME = "blog-style.json"
CATALOG_FILENAME = "blog-style-profiles.json"
MAX_PROFILE_BYTES = 64 * 1024
NAME_PATTERN = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) > 80 or not re.fullmatch(NAME_PATTERN, value):
        raise ValueError(f"{label} must be a safe short identifier (lowercase letters, digits and hyphens)")
    return value


def _validate_definition(value: object, label: str, *, scope: str) -> None:
    required = {"label", "scope", "description", "format_preset", "image_profile",
                "article_sequence", "text", "visual", "keep", "avoid", "uncertain"}
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError(f"{label} is missing required profile fields")
    _reject_unknown(value, required, label)
    if value["scope"] != scope:
        raise ValueError(f"{label}.scope must be {scope}")
    _text(value["label"], f"{label}.label", maximum=100)
    _text(value["description"], f"{label}.description", maximum=500)
    for key in ("format_preset", "image_profile"):
        _identifier(value[key], f"{label}.{key}")
    for key in ("article_sequence", "keep", "avoid", "uncertain"):
        _text_list(value[key], f"{label}.{key}")
    text = value["text"]
    text_required = {"body_alignment", "heading_alignment", "source_alignment", "body_size",
                     "body_line_spacing", "section_heading_size", "paragraph_max_sentences"}
    if not isinstance(text, dict) or not text_required <= set(text):
        raise ValueError(f"{label}.text is missing required fields")
    _reject_unknown(text, text_required | {"section_heading_style"}, f"{label}.text")
    for key in ("body_alignment", "heading_alignment", "source_alignment"):
        if not isinstance(text[key], str) or text[key] not in {"left", "center", "right", "justify"}:
            raise ValueError(f"{label}.text.{key} must be a supported alignment")
    for key, lower, upper in (("body_size", 10, 72), ("section_heading_size", 10, 72),
                              ("body_line_spacing", 1, 3), ("paragraph_max_sentences", 1, 10)):
        item = text[key]
        if (type(item) not in (int, float) or (type(item) is float and not math.isfinite(item))
                or not lower <= item <= upper or (key != "body_line_spacing" and item % 1 != 0)):
            raise ValueError(f"{label}.text.{key} must be a number in {lower}..{upper}")
    if "section_heading_style" in text and text["section_heading_style"] != "native-heading":
        raise ValueError(f"{label}.text.section_heading_style must be native-heading")
    visual = value["visual"]
    ratios = {"hero_ratio", "supporting_ratio", "step_ratio"}
    colors = {"primary", "accent", "muted", "table_header"}
    directions = {"composition", "palette", "base", "headline", "annotation", "annotations",
                  "series_rule", "provenance"}
    if not isinstance(visual, dict) or not {"hero_ratio", "composition"} <= set(visual):
        raise ValueError(f"{label}.visual is missing required fields")
    _reject_unknown(visual, ratios | colors | directions, f"{label}.visual")
    for key, item in visual.items():
        if key in ratios:
            if not isinstance(item, str) or item not in {"1:1", "16:9", "4:3", "4:5", "1.91:1"}:
                raise ValueError(f"{label}.visual.{key} must be a supported ratio")
        elif key in colors:
            if not isinstance(item, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item):
                raise ValueError(f"{label}.visual.{key} must use #RRGGBB")
        else:
            _text(item, f"{label}.visual.{key}", maximum=500)


def validate_local_profile(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("local profile must be an object")
    _reject_unknown(value, {"schema_version", "kind", "name", "definition"}, "local profile")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1 or value.get("kind") != "BlogStyleLocalProfile":
        raise ValueError("local profile must be BlogStyleLocalProfile v1")
    name = _identifier(value.get("name"), "name")
    if name in catalog()["profiles"]:
        raise ValueError("local profile name must not shadow a shipped profile")
    _validate_definition(value.get("definition"), "definition", scope="personal")
    return copy.deepcopy(value)


def _private_profile_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    # Do not resolve away links before inspecting them.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("local profile path must not contain a symbolic link")
    path = path.resolve(strict=False)
    plugin_root = Path(__file__).resolve().parent.parent
    if path.is_relative_to(plugin_root) or any((parent / ".git").exists() for parent in path.parents):
        raise ValueError("local profile must stay outside the repository and plugin")
    if any(part.lower() in {"cache", "caches", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache"}
           for part in path.parts):
        raise ValueError("local profile must stay outside cache directories")
    return path


def _check_profile_file(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("local profile must be a regular file")
    if info.st_nlink != 1:
        raise ValueError("local profile must not have hard links")
    if os.name == "posix":
        if info.st_uid != os.getuid():
            raise ValueError("local profile must belong to the current owner")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("local profile must have mode 0600")
    if info.st_size > MAX_PROFILE_BYTES:
        raise ValueError("local profile exceeds the 65536-byte limit")


def _read_local_profile(raw_path: str | Path) -> tuple[Path, dict[str, Any], str]:
    path = _private_profile_path(raw_path)
    before = path.lstat()
    _check_profile_file(before)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        _check_profile_file(opened)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("local profile changed while opening")
        raw = handle.read(MAX_PROFILE_BYTES + 1)
        after = os.fstat(handle.fileno())
        _check_profile_file(after)
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("local profile changed while reading")
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("local profile exceeds the 65536-byte limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("local profile must be bounded UTF-8 JSON") from exc
    return path, validate_local_profile(value), hashlib.sha256(raw).hexdigest()


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
    if len(value) > maximum:
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
    if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION or value.get("kind") != "BlogStyleCatalog":
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
        _identifier(name, "profile name")
        _validate_definition(profile, f"profiles.{name}", scope="universal")
    if default not in profiles:
        raise ValueError("default_profile must name a shipped profile")
    return copy.deepcopy(value)


def profile_names() -> tuple[str, ...]:
    return tuple(sorted(catalog()["profiles"]))


def validate_profile_name(value: object, *, data_dir: str | Path | None = None) -> str:
    name = _identifier(value, "profile name")
    if name in catalog()["profiles"]:
        return name
    path = config_path(data_dir)
    if path.exists() or path.is_symlink():
        selection = load_selection(data_dir)
        if selection["profile"] == name and "profile_file" in selection:
            return name
    raise ValueError("unsupported blog style profile; choose a shipped profile or explicitly confirm a matching local file")


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
    _reject_unknown(value, {"schema_version", "kind", "profile", "confirmed_at", "profile_file", "profile_sha256"}, "selection")
    if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION or value.get("kind") != "BlogStyleSelection":
        raise ValueError("blog style selection must be BlogStyleSelection v1")
    name = _identifier(value.get("profile"), "profile")
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "BlogStyleSelection",
        "profile": name,
        "confirmed_at": _timestamp(value.get("confirmed_at")),
    }
    if "profile_file" not in value:
        if "profile_sha256" in value:
            raise ValueError("profile_sha256 requires profile_file")
        if name not in catalog()["profiles"]:
            raise ValueError("blog style migration required: install the equivalent private profile and explicitly use set-file FILE --confirm")
        return result
    raw_path = value["profile_file"]
    if not isinstance(raw_path, str) or not raw_path or not Path(raw_path).is_absolute():
        raise ValueError("profile_file must be an absolute path")
    digest = value.get("profile_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("profile_sha256 must be a SHA-256 digest")
    path, local, actual_digest = _read_local_profile(raw_path)
    if local["name"] != name:
        raise ValueError("selected local profile name does not match profile file")
    if actual_digest != digest:
        raise ValueError("selected local profile file changed; explicit confirmation is required again")
    result.update(profile_file=str(path), profile_sha256=digest)
    return result


def load_selection(data_dir: str | Path | None = None) -> dict[str, Any]:
    path = config_path(data_dir)
    if path.is_symlink():
        raise ValueError("blog style selection path must not be a symbolic link")
    return validate_selection(json.loads(read_text_limited(path, extensions={".json"})))


def selected_profile_name(data_dir: str | Path | None = None) -> str:
    path = config_path(data_dir)
    if not path.exists() and not path.is_symlink():
        return str(catalog()["default_profile"])
    return load_selection(data_dir)["profile"]


def resolve_profile(profile: str | None = None, *, data_dir: str | Path | None = None) -> dict[str, Any]:
    if profile is not None:
        profile = _identifier(profile, "profile name")
    if profile is not None and profile in catalog()["profiles"]:
        name = profile
        result = copy.deepcopy(catalog()["profiles"][name])
    else:
        path = config_path(data_dir)
        if not path.exists() and not path.is_symlink():
            name = validate_profile_name(profile, data_dir=data_dir) if profile is not None else str(catalog()["default_profile"])
            result = copy.deepcopy(catalog()["profiles"][name])
        else:
            selection = load_selection(data_dir)
            name = selection["profile"]
            if profile is not None and profile != name:
                raise ValueError("unsupported blog style profile; local name must match the confirmed selection")
            if "profile_file" in selection:
                _, local, digest = _read_local_profile(selection["profile_file"])
                if digest != selection["profile_sha256"]:
                    raise ValueError("selected local profile file changed while resolving")
                result = local["definition"]
            else:
                result = copy.deepcopy(catalog()["profiles"][name])
    result["profile"] = name
    result["quality_floor"] = copy.deepcopy(catalog()["quality_floor"])
    return result


def profile_status(data_dir: str | Path | None = None) -> dict[str, Any]:
    path = config_path(data_dir)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "configured": path.exists() or path.is_symlink(),
        "path": str(path),
        "default_profile": catalog()["default_profile"],
    }
    if not result["configured"]:
        result.update({"profile": catalog()["default_profile"], "valid": True})
        return result
    try:
        selection = load_selection(data_dir)
        profile = resolve_profile(data_dir=data_dir)
        result.update({"profile": selection["profile"], "label": profile["label"], "scope": profile["scope"], "valid": True})
        if "profile_file" in selection:
            result["profile_file"] = selection["profile_file"]
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
        "profile": _identifier(profile, "profile"),
        "confirmed_at": confirmed_at or datetime.now(timezone.utc).isoformat(),
    }
    if profile not in catalog()["profiles"]:
        raise ValueError("unsupported shipped profile; use set-file for a local profile")
    normalized = validate_selection(value)
    return _save_selection(normalized, data_dir=data_dir)


def save_file_selection(
    profile_file: str | Path,
    *,
    data_dir: str | Path | None = None,
    confirmed: bool,
    confirmed_at: str | None = None,
) -> Path:
    if not confirmed:
        raise ValueError("explicit confirmation is required before saving a blog style")
    path, local, digest = _read_local_profile(profile_file)
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "BlogStyleSelection",
        "profile": local["name"],
        "confirmed_at": confirmed_at or datetime.now(timezone.utc).isoformat(),
        "profile_file": str(path),
        "profile_sha256": digest,
    }
    return _save_selection(validate_selection(value), data_dir=data_dir)


def _save_selection(normalized: dict[str, Any], *, data_dir: str | Path | None) -> Path:
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
    select_file = sub.add_parser("set-file")
    select_file.add_argument("file", type=Path)
    select_file.add_argument("--confirm", action="store_true")
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
        elif args.command == "set-file":
            saved = save_file_selection(args.file, data_dir=args.data_dir, confirmed=args.confirm)
            result = {"saved": True, **load_selection(args.data_dir), "path": str(saved)}
        else:
            result = {"reset": reset_selection(data_dir=args.data_dir, confirmed=args.confirm)}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
