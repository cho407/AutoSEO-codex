#!/usr/bin/env python3
"""Normalize, deduplicate, and score dated trend-research evidence."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from file_safety import read_text_limited
from korean_text import normalize_text, tokenize
from url_safety import validate_url

SCHEMA_VERSION = 1
WINDOW_HOURS = {"4h": 4, "24h": 24, "48h": 48, "7d": 24 * 7, "30d": 24 * 30}
REFRESH_HOURS = {"4h": 0.5, "24h": 2, "48h": 4, "7d": 6, "30d": 24}
ALLOWED_SOURCE_TYPES = {
    "official-trend",
    "primary-source",
    "news",
    "search-result",
    "first-party",
    "public-discussion",
}
ALLOWED_METRICS = {"velocity_index", "trend_index"}
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _bounded_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    text = normalize_text(value)
    if len(text) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return text


def _source_group(value: object, hostname: str) -> str:
    if value is None:
        group = hostname.casefold()
        for prefix in ("www.", "m.", "news."):
            if group.startswith(prefix):
                group = group[len(prefix) :]
                break
        return group
    group = _bounded_text(value, "source_group", 120).casefold()
    if not re.fullmatch(r"[0-9a-z가-힣._-]+", group):
        raise ValueError("source_group contains unsupported characters")
    return group


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value)
    filtered = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_PARAMETERS
        and not key.casefold().startswith("utm_")
    ]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("trend evidence URL contains an invalid port") from exc
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            (parsed.hostname or "").casefold()
            + (f":{port}" if port else ""),
            path,
            urlencode(sorted(filtered)),
            "",
        )
    )


def validate_trend_evidence(data: object) -> dict[str, Any]:
    """Return a normalized TrendEvidence v1 payload or raise ``ValueError``."""
    if not isinstance(data, dict):
        raise ValueError("trend evidence must be an object")
    value = copy.deepcopy(data)
    unknown = set(value) - {
        "schema_version",
        "kind",
        "topic",
        "market",
        "language",
        "window",
        "observed_at",
        "evidence",
    }
    if unknown:
        raise ValueError(f"unsupported trend evidence fields: {sorted(unknown)}")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version must be 1")
    if value.get("kind") != "TrendEvidence":
        raise ValueError("kind must be TrendEvidence")
    value["topic"] = _bounded_text(value.get("topic"), "topic", 300)
    value["market"] = _bounded_text(value.get("market"), "market", 30)
    value["language"] = _bounded_text(value.get("language"), "language", 30)
    if value.get("window") not in WINDOW_HOURS:
        raise ValueError(f"window must be one of {sorted(WINDOW_HOURS)}")
    observed_at = _parse_timestamp(value.get("observed_at"), "observed_at")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 100:
        raise ValueError("evidence must contain between 1 and 100 items")

    normalized: list[dict[str, Any]] = []
    future_limit = observed_at + timedelta(minutes=5)
    for index, raw in enumerate(evidence):
        label = f"evidence[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object")
        item = copy.deepcopy(raw)
        if item.get("source_type") not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"{label}.source_type is unsupported")
        url = item.get("url")
        if not isinstance(url, str) or not validate_url(url):
            raise ValueError(f"{label}.url must be a public HTTP(S) URL")
        item["canonical_url"] = canonicalize_url(url)
        hostname = urlsplit(item["canonical_url"]).hostname or ""
        item["source_group"] = _source_group(item.get("source_group"), hostname)
        item["title"] = _bounded_text(item.get("title"), f"{label}.title", 500)
        published = item.get("published_at")
        if published is not None:
            parsed = _parse_timestamp(published, f"{label}.published_at")
            if parsed > future_limit:
                raise ValueError(f"{label}.published_at is too far in the future")
            item["published_at"] = parsed.isoformat()
        elif item["source_type"] in {"news", "primary-source"}:
            raise ValueError(f"{label}.published_at is required for dated claims")
        event_at = item.get("event_at")
        if event_at is not None:
            parsed_event = _parse_timestamp(event_at, f"{label}.event_at")
            if parsed_event > future_limit:
                raise ValueError(f"{label}.event_at is too far in the future")
            item["event_at"] = parsed_event.isoformat()
        if "is_primary" in item and not isinstance(item["is_primary"], bool):
            raise ValueError(f"{label}.is_primary must be boolean")
        metrics = item.get("metrics", {})
        if not isinstance(metrics, dict):
            raise ValueError(f"{label}.metrics must be an object")
        unknown_metrics = set(metrics) - ALLOWED_METRICS
        if unknown_metrics:
            raise ValueError(f"{label}.metrics contains unsupported values")
        for name, metric in metrics.items():
            if (
                not isinstance(metric, (int, float))
                or isinstance(metric, bool)
                or not math.isfinite(metric)
            ):
                raise ValueError(f"{label}.metrics.{name} must be finite")
            if not 0 <= metric <= 100:
                raise ValueError(f"{label}.metrics.{name} must be between 0 and 100")
            metrics[name] = float(metric)
        item["metrics"] = metrics
        normalized.append(item)
    groups_by_host: dict[str, str] = {}
    for item in normalized:
        hostname = urlsplit(item["canonical_url"]).hostname or ""
        previous = groups_by_host.setdefault(hostname, item["source_group"])
        if previous != item["source_group"]:
            raise ValueError("one hostname must use one source_group within a trend capture")
    value["observed_at"] = observed_at.isoformat()
    value["evidence"] = normalized
    return value


def _headline_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", normalize_text(value).casefold())


def _deduplicate(evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen_urls: set[str] = set()
    seen_headlines: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    for item in evidence:
        url_key = item["canonical_url"]
        headline_key = (item["source_group"], _headline_key(item["title"]))
        if url_key in seen_urls or headline_key in seen_headlines:
            continue
        seen_urls.add(url_key)
        seen_headlines.add(headline_key)
        kept.append(item)
    return kept, len(evidence) - len(kept)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _opportunity_components(
    topic: str,
    evidence: list[dict[str, Any]],
    *,
    observed_at: datetime,
    window_hours: int,
) -> dict[str, float | None]:
    topic_tokens = {token for token in tokenize(topic) if len(token) > 1}
    relevance_values: list[float] = []
    for item in evidence:
        title_tokens = set(tokenize(item["title"]))
        relevance_values.append(
            len(topic_tokens & title_tokens) / max(1, len(topic_tokens)) * 100
        )
    freshness_values: list[float] = []
    for item in evidence:
        if not item.get("published_at"):
            continue
        published = _parse_timestamp(item["published_at"], "published_at")
        age_hours = max(0.0, (observed_at - published).total_seconds() / 3600)
        freshness_values.append(max(0.0, 100 - age_hours / window_hours * 100))
    groups = {item["source_group"] for item in evidence}
    corroboration = min(100.0, len(groups) / 3 * 100)
    velocity_values: list[float] = []
    for item in evidence:
        metrics = item.get("metrics", {})
        if "velocity_index" in metrics:
            velocity_values.append(metrics["velocity_index"])
        elif "trend_index" in metrics:
            velocity_values.append(metrics["trend_index"])
    return {
        "freshness": _mean(freshness_values),
        "relevance": _mean(relevance_values),
        "corroboration": round(corroboration, 1),
        "relative_velocity": _mean(velocity_values),
    }


def analyze_trends(
    data: object, *, as_of: str | datetime | None = None
) -> dict[str, Any]:
    value = validate_trend_evidence(data)
    evidence, duplicate_count = _deduplicate(value["evidence"])
    observed_at = _parse_timestamp(value["observed_at"], "observed_at")
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        current = as_of.astimezone(timezone.utc)
    elif isinstance(as_of, str):
        current = _parse_timestamp(as_of, "as_of")
    elif as_of is None:
        current = datetime.now(timezone.utc)
    else:
        raise ValueError("as_of must be a timestamp")
    groups = sorted({item["source_group"] for item in evidence})
    official_trend = any(item["source_type"] == "official-trend" for item in evidence)
    if len(groups) >= 2:
        corroboration_status = "confirmed"
    elif official_trend:
        corroboration_status = "measured-single-source"
    else:
        corroboration_status = "emerging-unconfirmed"

    window_hours = WINDOW_HOURS[value["window"]]
    components = _opportunity_components(
        value["topic"],
        evidence,
        observed_at=observed_at,
        window_hours=window_hours,
    )
    measured_components = {
        name: component for name, component in components.items() if component is not None
    }
    component_coverage = round(len(measured_components) / len(components) * 100, 1)
    opportunity_score = (
        round(sum(measured_components.values()) / len(measured_components), 1)
        if component_coverage >= 75 and measured_components
        else None
    )
    dated = [
        _parse_timestamp(item["published_at"], "published_at")
        for item in evidence
        if item.get("published_at")
    ]
    newest = max(dated) if dated else None
    stale = newest is None or (observed_at - newest).total_seconds() / 3600 > window_hours
    refresh_after = observed_at + timedelta(hours=REFRESH_HOURS[value["window"]])
    brief_ready = (
        corroboration_status == "confirmed"
        and not stale
        and opportunity_score is not None
        and opportunity_score >= 60
    )
    normalized_evidence = []
    for item in evidence:
        public_item = copy.deepcopy(item)
        public_item["url"] = public_item.pop("canonical_url")
        normalized_evidence.append(public_item)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "TrendReport",
        "topic": value["topic"],
        "market": value["market"],
        "language": value["language"],
        "window": value["window"],
        "observed_at": value["observed_at"],
        "evidence_count": len(evidence),
        "duplicate_count": duplicate_count,
        "independent_source_count": len(groups),
        "source_groups": groups,
        "corroboration_status": corroboration_status,
        "freshness": {
            "newest_published_at": newest.isoformat() if newest else None,
            "oldest_published_at": min(dated).isoformat() if dated else None,
            "stale_for_window": stale,
        },
        "opportunity": {
            "score": opportunity_score,
            "score_displayed": opportunity_score is not None,
            "component_coverage_percent": component_coverage,
            "components": components,
            "method": "equal average of measured freshness, topic relevance, corroboration, and relative velocity",
            "meaning": "content-research priority, not absolute popularity or ranking potential",
            "exact_search_volume": None,
        },
        "refresh": {
            "refresh_after": refresh_after.isoformat(),
            "needs_refresh": current > refresh_after,
        },
        "content_action": "brief-ready" if brief_ready else "corroborate-before-brief",
        "evidence": normalized_evidence,
        "limitations": [
            "Trend evidence is a dated sample and can change after capture.",
            "Relative indices from different methods or markets are not directly comparable.",
            "The report does not infer exact search volume, traffic, rank, or future demand.",
        ],
    }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("input", type=Path)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--as-of")
    args = parser.parse_args(argv)
    try:
        data = _load(args.input)
        if args.command == "validate":
            result: object = {"valid": True, "evidence": validate_trend_evidence(data)}
        else:
            result = analyze_trends(data, as_of=args.as_of)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
