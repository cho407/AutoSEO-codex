#!/usr/bin/env python3
"""Validate and score transparent search evidence gathered by Codex or the user."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from file_safety import read_text_limited
from korean_text import classify_intent, tokenize
from readiness_evidence import timestamp
from url_safety import validate_url

ALLOWED_RESULT_TYPES = {
    "organic",
    "image",
    "video",
    "news",
    "map",
    "discussion",
    "shopping",
    "ai-citation",
}
def _tokens(value: str) -> set[str]:
    return {token for token in tokenize(value) if len(token) > 1}


def _load(path: str | Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("search evidence must be a JSON object")
    return value


def validate_evidence(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(data.get("query"), str) or not data["query"].strip():
        errors.append("query must be a non-empty string")
    if not isinstance(data.get("captured_at"), str) or not data["captured_at"].strip():
        errors.append("captured_at must be a non-empty timestamp string")
    results = data.get("results")
    if not isinstance(results, list) or not 1 <= len(results) <= 100:
        errors.append("results must contain between 1 and 100 entries")
        return errors

    seen_positions: set[int] = set()
    for index, item in enumerate(results):
        label = f"results[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        position = item.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position < 1:
            errors.append(f"{label}.position must be a positive integer")
        elif position in seen_positions:
            errors.append(f"duplicate position: {position}")
        else:
            seen_positions.add(position)
        url = item.get("url")
        if not isinstance(url, str) or not validate_url(url):
            errors.append(f"{label}.url must be a public HTTP(S) URL")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            errors.append(f"{label}.title must be non-empty")
        if item.get("result_type") not in ALLOWED_RESULT_TYPES:
            errors.append(f"{label}.result_type is unsupported")

    signals = data.get("signals", {})
    if not isinstance(signals, dict):
        errors.append("signals must be an object when present")
    else:
        for key, value in signals.items():
            try:
                finite = math.isfinite(value)
            except (TypeError, OverflowError):
                finite = False
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not finite
                or value < 0
            ):
                errors.append(f"signals.{key} must be a non-negative number")
    return errors


def _demand_proxy(signals: dict[str, float]) -> dict[str, Any]:
    components: list[tuple[str, float]] = []
    if "gsc_impressions" in signals:
        components.append(
            ("gsc_impressions", min(100.0, math.log1p(signals["gsc_impressions"]) / math.log(10001) * 100))
        )
    if "autosuggest_count" in signals:
        components.append(("autosuggest_count", min(100.0, signals["autosuggest_count"] * 5)))
    if "trends_index" in signals:
        components.append(("trends_index", min(100.0, signals["trends_index"])))
    if "observed_mentions" in signals:
        components.append(("observed_mentions", min(100.0, signals["observed_mentions"] * 4)))

    if not components:
        return {
            "score": None,
            "confidence": "low",
            "inputs": [],
            "note": "No demand signals were supplied; exact volume is not inferred.",
        }
    score = round(sum(value for _, value in components) / len(components), 1)
    confidence = "high" if len(components) >= 3 else "medium" if len(components) == 2 else "low"
    return {
        "score": score,
        "confidence": confidence,
        "inputs": [name for name, _ in components],
        "note": "Relative demand proxy; compare only captures with the same method and market.",
    }


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    errors = validate_evidence(data)
    if errors:
        raise ValueError("; ".join(errors))

    query_tokens = _tokens(data["query"])
    results = sorted(data["results"], key=lambda item: item["position"])
    domains = [urlparse(item["url"]).hostname or "" for item in results]
    result_types = Counter(item["result_type"] for item in results)
    title_coverages = [
        len(query_tokens & _tokens(item["title"])) / max(1, len(query_tokens)) for item in results
    ]
    title_alignment = sum(title_coverages) / len(title_coverages)
    domain_diversity = len(set(domains)) / len(domains)
    feature_diversity = min(1.0, len(result_types) / 5)
    commercial_share = sum(
        item["result_type"] in {"shopping", "map"} for item in results
    ) / len(results)
    competition_proxy = round(
        min(
            100.0,
            title_alignment * 45
            + domain_diversity * 25
            + feature_diversity * 20
            + commercial_share * 10,
        ),
        1,
    )

    intent_result = classify_intent(data["query"])
    intent = intent_result["primary"]
    if intent == "mixed-or-unclear" and result_types["map"]:
        intent = "local"
    elif intent == "mixed-or-unclear" and result_types["shopping"]:
        intent = "transactional"

    signals = {key: float(value) for key, value in data.get("signals", {}).items()}
    return {
        "schema_version": 1,
        "method": "transparent-public-signal-proxy",
        "query": data["query"],
        "captured_at": data["captured_at"],
        "market": data.get("market"),
        "result_count": len(results),
        "unique_domains": len(set(domains)),
        "result_types": dict(sorted(result_types.items())),
        "intent": intent,
        "intent_evidence": intent_result,
        "competition_proxy": competition_proxy,
        "competition_inputs": {
            "title_alignment": round(title_alignment, 3),
            "domain_diversity": round(domain_diversity, 3),
            "result_feature_diversity": round(feature_diversity, 3),
        },
        "demand_proxy": _demand_proxy(signals),
        "exact_search_volume": None,
        "limitations": [
            "This is not a proprietary keyword-volume or authority metric.",
            "Search results vary by time, location, language, device, and personalization.",
        ],
    }


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_result = analyze(left)
    right_result = analyze(right)
    dimensions = ("query", "market", "language", "device", "surface", "method", "window", "sample_limit")
    mismatches = [key for key in dimensions if left.get(key) != right.get(key)]
    missing = [key for key in dimensions if left.get(key) is None or right.get(key) is None]
    left_time, right_time = timestamp(left["captured_at"]), timestamp(right["captured_at"])
    if mismatches or missing or right_time <= left_time:
        return {
            "comparable": False, "competition_proxy_change": None,
            "new_urls": None, "lost_urls": None, "retained_urls": None,
            "reason": "Comparison requires matching query/market/language/device/surface/method/window/sample limit and a later capture.",
            "mismatched_dimensions": mismatches, "missing_dimensions": missing,
        }
    left_urls = {item["url"] for item in left["results"]}
    right_urls = {item["url"] for item in right["results"]}
    return {
        "comparable": True,
        "query": right_result["query"],
        "from": left_result["captured_at"],
        "to": right_result["captured_at"],
        "new_urls": sorted(right_urls - left_urls),
        "lost_urls": sorted(left_urls - right_urls),
        "retained_urls": sorted(left_urls & right_urls),
        "competition_proxy_change": round(
            right_result["competition_proxy"] - left_result["competition_proxy"], 1
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("input")
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("input")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("baseline")
    compare_parser.add_argument("current")
    for child in (validate_parser, analyze_parser, compare_parser):
        child.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            errors = validate_evidence(_load(args.input))
            result: Any = {"valid": not errors, "errors": errors}
            code = 0 if not errors else 2
        elif args.command == "analyze":
            result = analyze(_load(args.input))
            code = 0
        else:
            result = compare(_load(args.baseline), _load(args.current))
            code = 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"search evidence error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
