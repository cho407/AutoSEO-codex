#!/usr/bin/env python3
"""Create and compare local backlink snapshots without an external data subscription."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from file_safety import read_text_limited, write_text_safely
from url_safety import validate_url


def _canonical_url(value: str) -> str:
    if not isinstance(value, str) or not validate_url(value):
        raise ValueError("backlink URLs must be public HTTP(S) URLs")
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _load(path: str | Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if isinstance(value, list):
        return {"schema_version": 1, "links": value}
    if not isinstance(value, dict):
        raise ValueError("backlink snapshot must be a JSON object or array")
    return value


def normalize_snapshot(data: dict[str, Any], *, target: str | None = None) -> dict[str, Any]:
    if data.get("schema_version", 1) != 1:
        raise ValueError("schema_version must be 1")
    raw_links = data.get("links")
    if not isinstance(raw_links, list):
        raise ValueError("links must be an array")
    if len(raw_links) > 10_000:
        raise ValueError("links exceeds the 10,000-entry safety limit")

    resolved_target = target or data.get("target")
    canonical_target = _canonical_url(resolved_target) if resolved_target else None
    links: dict[tuple[str, str], dict[str, Any]] = {}
    for index, item in enumerate(raw_links):
        if not isinstance(item, dict):
            raise ValueError(f"links[{index}] must be an object")
        source_url = _canonical_url(item.get("source_url", ""))
        item_target = item.get("target_url") or canonical_target
        if not item_target:
            raise ValueError(f"links[{index}].target_url is required")
        target_url = _canonical_url(item_target)
        if canonical_target and target_url != canonical_target:
            raise ValueError(f"links[{index}].target_url does not match snapshot target")
        normalized = {
            "source_url": source_url,
            "target_url": target_url,
        }
        for field in ("anchor_text", "rel", "status"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                normalized[field] = value.strip()
        links[(source_url, target_url)] = normalized

    if canonical_target is None and links:
        targets = {key[1] for key in links}
        if len(targets) != 1:
            raise ValueError("snapshot links must share one target unless target is specified")
        canonical_target = next(iter(targets))
    return {
        "schema_version": 1,
        "target": canonical_target,
        "captured_at": data.get("captured_at"),
        "links": [links[key] for key in sorted(links)],
    }


def compare_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    left = normalize_snapshot(baseline)
    right = normalize_snapshot(current)
    if left["target"] != right["target"]:
        raise ValueError("baseline and current snapshots must have the same target")

    left_links = {
        (item["source_url"], item["target_url"]): item for item in left["links"]
    }
    right_links = {
        (item["source_url"], item["target_url"]): item for item in right["links"]
    }
    new_keys = sorted(right_links.keys() - left_links.keys())
    lost_keys = sorted(left_links.keys() - right_links.keys())
    retained_keys = sorted(left_links.keys() & right_links.keys())
    return {
        "schema_version": 1,
        "target": right["target"],
        "baseline_at": left.get("captured_at"),
        "current_at": right.get("captured_at"),
        "counts": {
            "new": len(new_keys),
            "lost": len(lost_keys),
            "retained": len(retained_keys),
        },
        "new": [right_links[key] for key in new_keys],
        "lost": [left_links[key] for key in lost_keys],
        "retained": [right_links[key] for key in retained_keys],
        "limitations": [
            "Changes reflect only links present in the supplied snapshots.",
            "A missing source can mean discovery coverage changed; verify before remediation.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("input")
    snapshot.add_argument("output")
    snapshot.add_argument("--target")
    snapshot.add_argument("--overwrite", action="store_true")
    compare = subparsers.add_parser("compare")
    compare.add_argument("baseline")
    compare.add_argument("current")
    validate = subparsers.add_parser("validate")
    validate.add_argument("input")
    for child in (snapshot, compare, validate):
        child.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "snapshot":
            value = normalize_snapshot(_load(args.input), target=args.target)
            value["captured_at"] = datetime.now(timezone.utc).isoformat()
            output = write_text_safely(
                args.output,
                json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                overwrite=args.overwrite,
                extensions={".json"},
            )
            result: Any = {
                "output": str(output),
                "target": value["target"],
                "link_count": len(value["links"]),
            }
        elif args.command == "compare":
            result = compare_snapshots(_load(args.baseline), _load(args.current))
        else:
            value = normalize_snapshot(_load(args.input))
            result = {"valid": True, "target": value["target"], "link_count": len(value["links"])}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"backlink history error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
