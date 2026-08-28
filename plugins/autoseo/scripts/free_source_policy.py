#!/usr/bin/env python3
"""Validate and inspect AutoSEO's no-subscription evidence-source catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "free-sources.json"
ALLOWED_ACCESS = {"public", "codex-native", "free-account", "local"}
REQUIRED_FIELDS = {
    "id",
    "name",
    "access",
    "subscription_required",
    "official_url",
    "use_cases",
    "limitations",
}


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source catalog must be a JSON object")
    return value


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def validate_catalog(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    sources = data.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be an array")
        sources = []

    seen: set[str] = set()
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_FIELDS - set(source)
        if missing:
            errors.append(f"{label} missing fields: {sorted(missing)}")
            continue
        source_id = source["id"]
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}.id must be non-empty")
        elif source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        else:
            seen.add(source_id)
        if source["access"] not in ALLOWED_ACCESS:
            errors.append(f"{label}.access must be one of {sorted(ALLOWED_ACCESS)}")
        if source["subscription_required"] is not False:
            errors.append(f"{label}.subscription_required must be false")
        parsed = urlparse(source["official_url"])
        if parsed.scheme != "https" or not parsed.hostname:
            errors.append(f"{label}.official_url must be an absolute HTTPS URL")
        for field in ("use_cases", "limitations"):
            if not _nonempty_strings(source[field]):
                errors.append(f"{label}.{field} must be a non-empty string array")

    if len(sources) < 10:
        errors.append("at least 10 independent evidence sources are required")
    return {"valid": not errors, "source_count": len(sources), "errors": errors}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "catalog", "show"))
    parser.add_argument("source_id", nargs="?")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        data = load_catalog()
        validation = validate_catalog(data)
        if not validation["valid"]:
            print(json.dumps(validation, indent=2), file=sys.stderr)
            return 2
        if args.command == "validate":
            result: Any = validation
        elif args.command == "catalog":
            result = data["sources"]
        else:
            if not args.source_id:
                raise ValueError("show requires source_id")
            result = next(
                (item for item in data["sources"] if item["id"] == args.source_id),
                None,
            )
            if result is None:
                raise ValueError(f"unknown source: {args.source_id}")
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif isinstance(result, list):
            for item in result:
                print(f"{item['id']}: {item['name']} [{item['access']}]")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"free source policy error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
