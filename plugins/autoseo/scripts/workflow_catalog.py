#!/usr/bin/env python3
"""Validate, browse, select, export, and refresh AutoSEO workflow playbooks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from file_safety import write_text_safely
from requests import RequestException
from url_safety import URLSafetyError, safe_requests_get

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "workflow-playbooks.json"
OFFICIAL_SOURCE = (
    "https://raw.githubusercontent.com/HarrisonCho407/AutoSEO-codex/"
    "main/plugins/autoseo/data/workflow-playbooks.json"
)
EXPECTED_STAGES = {"find": 5, "leverage": 1, "optimize": 21, "win": 3, "local": 11}
MAX_CATALOG_BYTES = 2 * 1024 * 1024
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]+", re.IGNORECASE)


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("workflow catalog must be a JSON object")
    return value


def validate_catalog(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    playbooks = data.get("playbooks")
    if not isinstance(playbooks, list):
        errors.append("playbooks must be an array")
        playbooks = []

    counts: Counter[str] = Counter()
    seen: set[str] = set()
    required = ("id", "stage", "title", "triggers", "questions", "deliverables", "verification")
    for index, item in enumerate(playbooks):
        if not isinstance(item, dict):
            errors.append(f"playbooks[{index}] must be an object")
            continue
        playbook_id = item.get("id")
        if not isinstance(playbook_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", playbook_id):
            errors.append(f"playbooks[{index}].id is invalid")
        elif playbook_id in seen:
            errors.append(f"duplicate playbook id: {playbook_id}")
        else:
            seen.add(playbook_id)
        stage = item.get("stage")
        if stage not in EXPECTED_STAGES:
            errors.append(f"playbooks[{index}].stage is invalid")
        else:
            counts[stage] += 1
        for key in required[2:]:
            value = item.get(key)
            if key == "title":
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"playbooks[{index}].title must be non-empty")
            elif not isinstance(value, list) or not value or not all(
                isinstance(entry, str) and entry.strip() for entry in value
            ):
                errors.append(f"playbooks[{index}].{key} must be a non-empty string array")

    if len(playbooks) != 41:
        errors.append(f"expected 41 playbooks, found {len(playbooks)}")
    if dict(counts) != EXPECTED_STAGES:
        errors.append(f"stage counts must be {EXPECTED_STAGES}, found {dict(counts)}")
    return {
        "valid": not errors,
        "playbook_count": len(playbooks),
        "stage_counts": dict(sorted(counts.items())),
        "errors": errors,
    }


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value)}


def recommend(data: dict[str, Any], context: str, *, stage: str | None, limit: int) -> list[dict[str, Any]]:
    query = _tokens(context)
    candidates = [
        item for item in data["playbooks"] if stage is None or item["stage"] == stage
    ]

    def score(item: dict[str, Any]) -> tuple[int, str]:
        searchable = " ".join(
            [item["id"], item["title"], *item["triggers"], *item["questions"]]
        )
        overlap = len(query & _tokens(searchable))
        trigger_bonus = sum(2 for trigger in item["triggers"] if trigger.lower() in context.lower())
        return overlap + trigger_bonus, item["id"]

    ranked = sorted(candidates, key=lambda item: (-score(item)[0], score(item)[1]))
    return ranked[:limit]


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        json.dump(value, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    if isinstance(value, list):
        for item in value:
            print(f"{item['id']}: {item['title']} [{item['stage']}]")
        return
    if isinstance(value, dict) and "title" in value:
        print(f"{value['title']} ({value['id']}, {value['stage']})")
        for key in ("questions", "deliverables", "verification"):
            print(f"\n{key.replace('_', ' ').title()}:")
            for entry in value[key]:
                print(f"- {entry}")
        return
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _official_source(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "raw.githubusercontent.com"
            and parsed.port is None
            and parsed.path
            == "/HarrisonCho407/AutoSEO-codex/main/plugins/autoseo/data/"
            "workflow-playbooks.json"
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def _refresh(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_network:
        raise ValueError("refresh requires --confirm-network after explicit user approval")
    if not _official_source(args.source):
        raise ValueError("refresh source must be the official AutoSEO catalog URL")
    response = safe_requests_get(
        args.source,
        timeout=20,
        max_response_bytes=MAX_CATALOG_BYTES,
        allow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("remote catalog must be a JSON object")
    validation = validate_catalog(data)
    if not validation["valid"]:
        raise ValueError("remote catalog validation failed: " + "; ".join(validation["errors"]))
    destination = write_text_safely(
        args.output,
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        overwrite=args.overwrite,
        extensions={".json"},
    )
    return {**validation, "source": args.source, "output": str(destination)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("validate", "overview"):
        child = subparsers.add_parser(command)
        child.add_argument("--json", action="store_true")

    catalog = subparsers.add_parser("catalog")
    catalog.add_argument("--stage", choices=tuple(EXPECTED_STAGES))
    catalog.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show")
    show.add_argument("playbook_id")
    show.add_argument("--json", action="store_true")

    choose = subparsers.add_parser("recommend")
    choose.add_argument("context")
    choose.add_argument("--stage", choices=tuple(EXPECTED_STAGES))
    choose.add_argument("--limit", type=int, default=3, choices=range(1, 11))
    choose.add_argument("--json", action="store_true")

    export = subparsers.add_parser("export")
    export.add_argument("output")
    export.add_argument("--stage", choices=tuple(EXPECTED_STAGES))
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--json", action="store_true")

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--source", default=OFFICIAL_SOURCE)
    refresh.add_argument("--output", required=True)
    refresh.add_argument("--confirm-network", action="store_true")
    refresh.add_argument("--overwrite", action="store_true")
    refresh.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "refresh":
            _emit(_refresh(args), as_json=args.json)
            return 0

        data = load_catalog()
        validation = validate_catalog(data)
        if not validation["valid"]:
            _emit(validation, as_json=True)
            return 2
        if args.command == "validate":
            _emit(validation, as_json=args.json)
        elif args.command == "overview":
            _emit(
                {
                    "name": data["name"],
                    "description": data["description"],
                    **validation,
                },
                as_json=args.json,
            )
        elif args.command == "catalog":
            items = [
                item for item in data["playbooks"] if args.stage is None or item["stage"] == args.stage
            ]
            _emit(items, as_json=args.json)
        elif args.command == "show":
            item = next(
                (entry for entry in data["playbooks"] if entry["id"] == args.playbook_id),
                None,
            )
            if item is None:
                raise ValueError(f"unknown playbook: {args.playbook_id}")
            _emit(item, as_json=args.json)
        elif args.command == "recommend":
            _emit(
                recommend(data, args.context, stage=args.stage, limit=args.limit),
                as_json=args.json,
            )
        elif args.command == "export":
            items = [
                item for item in data["playbooks"] if args.stage is None or item["stage"] == args.stage
            ]
            payload = {**data, "playbooks": items}
            destination = write_text_safely(
                args.output,
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                overwrite=args.overwrite,
                extensions={".json"},
            )
            _emit({"output": str(destination), "playbook_count": len(items)}, as_json=args.json)
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RequestException, URLSafetyError) as exc:
        print(f"workflow catalog error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
