#!/usr/bin/env python3
"""Independent SEO, AEO, GEO, LLMO, and NEO readiness reports."""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from evidence_engine import EvidenceEngine
from file_safety import read_text_limited
from korean_text import classify_intent

SCHEMA_VERSION = 1
ALL_LANES = ("seo", "aeo", "geo", "llmo", "neo")
SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}
STATUSES = {"pass", "fail", "unmeasured"}
MINIMUM_COVERAGE_PERCENT = 70.0

_INFORMATIONAL_TERMS = {
    "what",
    "why",
    "how",
    "when",
    "guide",
    "tutorial",
    "무엇",
    "뭐",
    "왜",
    "어떻게",
    "방법",
    "가이드",
    "알려",
}
_BRAND_AI_TERMS = {
    "brand",
    "citation",
    "citations",
    "chatgpt",
    "perplexity",
    "ai visibility",
    "브랜드",
    "인용",
    "언급",
    "생성형 검색",
}
_KOREA_TERMS = {"naver", "네이버", "한국", "국내", "대한민국"}
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,63}$", re.IGNORECASE)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _looks_like_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _contains_korean(value: str) -> bool:
    return any("가" <= char <= "힣" for char in value)


def select_lanes(
    target: str,
    *,
    market: str | None = None,
    language: str | None = None,
    request: str | None = None,
    run_all: bool = False,
) -> tuple[str, ...]:
    """Select lanes from the published deterministic routing contract."""
    if run_all:
        return ALL_LANES
    target_text = target.strip()
    combined = " ".join(filter(None, (target_text, request or ""))).casefold()
    selected: set[str] = set()
    is_url = _looks_like_url(target_text)
    if is_url:
        selected.add("seo")
    tokens = set(re.findall(r"[\w가-힣-]+", combined))
    if "?" in combined or tokens & _INFORMATIONAL_TERMS:
        selected.add("aeo")
    brand_request = any(term in combined for term in _BRAND_AI_TERMS)
    if brand_request or (not is_url and _DOMAIN_RE.fullmatch(target_text)):
        selected.update(("geo", "llmo"))
    korea_target = (
        (market or "").casefold() in {"kr", "ko-kr", "korea", "south korea"}
        or (language or "").casefold().startswith("ko")
        or _contains_korean(combined)
        or any(term in combined for term in _KOREA_TERMS)
    )
    if korea_target:
        selected.add("neo")
    return tuple(lane for lane in ALL_LANES if lane in selected)


def _validate_check(check: dict[str, Any]) -> None:
    if check.get("status") not in STATUSES:
        raise ValueError(f"unsupported check status: {check.get('status')}")
    if check.get("severity") not in SEVERITY_WEIGHTS:
        raise ValueError(f"unsupported severity: {check.get('severity')}")
    if not isinstance(check.get("id"), str) or not check["id"]:
        raise ValueError("each lane check requires an id")


def score_checks(checks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Score measured checks without turning unmeasured evidence into zero."""
    values = [copy.deepcopy(check) for check in checks]
    for check in values:
        _validate_check(check)
    applicable = [check for check in values if check.get("applicable", True)]
    measured = [check for check in applicable if check["status"] != "unmeasured"]
    denominator = sum(SEVERITY_WEIGHTS[check["severity"]] for check in applicable)
    measured_weight = sum(SEVERITY_WEIGHTS[check["severity"]] for check in measured)
    pass_weight = sum(
        SEVERITY_WEIGHTS[check["severity"]]
        for check in measured
        if check["status"] == "pass"
    )
    fail_weight = sum(
        SEVERITY_WEIGHTS[check["severity"]]
        for check in measured
        if check["status"] == "fail"
    )
    unmeasured_weight = denominator - measured_weight
    coverage = round(measured_weight / denominator * 100, 1) if denominator else 0.0
    required_unmeasured = [
        check["id"]
        for check in applicable
        if check.get("required") and check["status"] == "unmeasured"
    ]
    score: float | None = None
    reason: str | None = None
    if required_unmeasured:
        reason = "required eligibility checks are unmeasured: " + ", ".join(
            required_unmeasured
        )
    elif coverage < MINIMUM_COVERAGE_PERCENT:
        reason = (
            f"evidence coverage {coverage:.1f}% is below the "
            f"{MINIMUM_COVERAGE_PERCENT:.0f}% display threshold"
        )
    elif measured_weight:
        score = round(pass_weight / measured_weight * 100, 1)
    else:
        reason = "no applicable evidence was measured"
    return {
        "score": score,
        "score_displayed": score is not None,
        "coverage_percent": coverage,
        "coverage_threshold_percent": MINIMUM_COVERAGE_PERCENT,
        "pass_weight": pass_weight,
        "fail_weight": fail_weight,
        "unmeasured_weight": unmeasured_weight,
        "applicable_weight": denominator,
        "reason": reason,
        "meaning": "readiness only; not an exposure, ranking, or citation guarantee",
    }


def _observation(
    readiness: dict[str, Any],
    *,
    market: str | None,
    language: str | None,
    surface: str,
    measured_at: str,
) -> dict[str, Any]:
    confidence = (
        "high"
        if readiness["coverage_percent"] >= 90
        else "medium"
        if readiness["coverage_percent"] >= MINIMUM_COVERAGE_PERCENT
        else "low"
    )
    return {
        "metric": "weighted_evidence_coverage",
        "numerator": readiness["applicable_weight"] - readiness["unmeasured_weight"],
        "denominator": readiness["applicable_weight"],
        "market": market,
        "language": language,
        "surface": surface,
        "measured_at": measured_at,
        "confidence": confidence,
        "limitations": [
            "Readiness checks describe observable preparation, not guaranteed visibility."
        ],
    }


def _normalize_outcomes(
    outcomes: Iterable[dict[str, Any]],
    *,
    market: str | None,
    language: str | None,
    surface: str,
    measured_at: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for outcome in outcomes:
        item = copy.deepcopy(outcome)
        item.setdefault("numerator", None)
        item.setdefault("denominator", None)
        item.setdefault("market", market)
        item.setdefault("language", language)
        item.setdefault("surface", surface)
        item.setdefault("measured_at", measured_at)
        item.setdefault("confidence", "low")
        item.setdefault("limitations", ["Bounded observation; not exhaustive monitoring."])
        normalized.append(item)
    return normalized


def build_lane_report(
    lane: str,
    target: str,
    checks: Iterable[dict[str, Any]],
    *,
    outcomes: Iterable[dict[str, Any]],
    market: str | None = None,
    language: str | None = None,
    surface: str | None = None,
    measured_at: str | None = None,
) -> dict[str, Any]:
    if lane not in ALL_LANES:
        raise ValueError(f"unsupported lane: {lane}")
    check_list = [copy.deepcopy(check) for check in checks]
    readiness = score_checks(check_list)
    captured_at = measured_at or _utc_now()
    lane_surface = surface or f"{lane}-readiness"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "LaneReport",
        "lane": lane,
        "target": target,
        "measured_at": captured_at,
        "readiness": readiness,
        "checks": check_list,
        "outcomes": _normalize_outcomes(
            outcomes,
            market=market,
            language=language,
            surface=lane_surface,
            measured_at=captured_at,
        ),
        "observations": [
            _observation(
                readiness,
                market=market,
                language=language,
                surface=lane_surface,
                measured_at=captured_at,
            )
        ],
        "limitations": [
            "The score is withheld when mandatory eligibility is unknown or evidence coverage is below 70%.",
            "Actual clicks, rankings, mentions, and citations stay in the outcomes panel.",
        ],
    }


def _check(
    identifier: str,
    status: str,
    severity: str,
    evidence: object,
    *,
    required: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    item = {
        "id": identifier,
        "status": status,
        "severity": severity,
        "applicable": True,
        "required": required,
        "evidence": evidence if isinstance(evidence, list) else [evidence],
    }
    if note:
        item["note"] = note
    return item


def _seo_checks(bundle: dict[str, Any], _: str) -> list[dict[str, Any]]:
    source = bundle.get("source_response", {})
    metadata = bundle.get("metadata", {})
    content = bundle.get("content", {})
    status_code = source.get("status_code")
    reachable = isinstance(status_code, int) and 200 <= status_code < 400
    robots = str(metadata.get("meta_robots") or "").casefold()
    return [
        _check("http_reachable", "pass" if reachable else "fail", "critical", status_code, required=True),
        _check(
            "index_eligible",
            "unmeasured" if not reachable else "fail" if "noindex" in robots else "pass",
            "critical",
            metadata.get("meta_robots"),
            required=True,
        ),
        _check("title", "pass" if metadata.get("title") else "fail", "high", metadata.get("title")),
        _check("canonical", "pass" if metadata.get("canonical") else "fail", "medium", metadata.get("canonical")),
        _check("primary_heading", "pass" if metadata.get("h1") else "fail", "medium", metadata.get("h1", [])),
        _check("substantive_content", "pass" if content.get("text_chars", 0) >= 300 else "fail", "high", content.get("text_chars", 0)),
    ]


def _aeo_checks(bundle: dict[str, Any], target: str) -> list[dict[str, Any]]:
    content = bundle.get("content", {})
    metadata = bundle.get("metadata", {})
    text = str(content.get("text") or "")
    headings = [*metadata.get("h1", []), *metadata.get("h2", []), *metadata.get("h3", [])]
    question_aligned = "?" in target or any("?" in str(value) for value in headings)
    return [
        _check("answerable_content", "pass" if text else "fail", "critical", len(text), required=True),
        _check("question_intent_alignment", "pass" if question_aligned else "fail", "medium", headings),
        _check("direct_answer", "pass" if len(text[:400].strip()) >= 20 else "fail", "high", text[:400]),
        _check("claim_source_support", "pass" if bundle.get("links", {}).get("external") else "fail", "high", bundle.get("links", {}).get("external", [])[:5]),
        _check("authorship", "pass" if any(item.get("type") == "Person" for item in bundle.get("entities", [])) else "fail", "medium", bundle.get("entities", [])),
    ]


def _geo_checks(bundle: dict[str, Any], _: str) -> list[dict[str, Any]]:
    source = bundle.get("source_response", {})
    render = bundle.get("render", {})
    public = source.get("status_code") == 200 and not source.get("error")
    render_ok = not render.get("is_spa") or (
        render.get("attempted") and not render.get("error")
    )
    return [
        _check("public_search_access", "pass" if public else "fail", "critical", source, required=True),
        _check(
            "search_crawler_policy",
            "unmeasured",
            "critical",
            [],
            note="Requires a dated robots.txt check for the named search crawler.",
        ),
        _check("source_support", "pass" if bundle.get("links", {}).get("external") else "fail", "high", bundle.get("links", {}).get("external", [])[:5]),
        _check("entity_clarity", "pass" if bundle.get("entities") else "fail", "medium", bundle.get("entities", [])),
        _check("render_access", "pass" if render_ok else "fail", "high", render),
    ]


def _llmo_checks(bundle: dict[str, Any], _: str) -> list[dict[str, Any]]:
    entities = bundle.get("entities", [])
    external = bundle.get("links", {}).get("external", [])
    return [
        _check("brand_fact_ledger", "pass" if entities else "fail", "critical", entities, required=True),
        _check("external_corroboration", "pass" if external else "fail", "high", external[:5]),
        _check(
            "closed_book_model_knowledge",
            "unmeasured",
            "critical",
            [],
            required=True,
            note="Search-disabled model state was not guaranteed.",
        ),
    ]


def _neo_checks(bundle: dict[str, Any], target: str) -> list[dict[str, Any]]:
    source = bundle.get("source_response", {})
    language = str(bundle.get("content", {}).get("language") or "")
    neo_evidence = bundle.get("neo_evidence", {})
    intent = classify_intent(target)
    yeti = neo_evidence.get("yeti_allowed")
    feed = neo_evidence.get("rss_or_sitemap")
    return [
        _check("public_naver_access", "pass" if source.get("status_code") == 200 else "fail", "critical", source, required=True),
        _check("korean_language", "pass" if language.startswith("ko") else "fail", "high", language),
        _check("korean_intent", "pass" if intent["primary"] != "mixed-or-unclear" else "fail", "medium", intent),
        _check(
            "yeti_policy",
            "unmeasured" if not isinstance(yeti, bool) else "pass" if yeti else "fail",
            "critical",
            yeti,
            note="Requires a dated robots.txt observation.",
        ),
        _check(
            "rss_or_sitemap",
            "unmeasured" if not isinstance(feed, bool) else "pass" if feed else "fail",
            "medium",
            feed,
            note="Requires site-level discovery evidence.",
        ),
        _check("naver_search_or_ai_briefing", "unmeasured", "high", [], note="Requires a reproducible Naver result sample."),
    ]


_ANALYZERS = {
    "seo": _seo_checks,
    "aeo": _aeo_checks,
    "geo": _geo_checks,
    "llmo": _llmo_checks,
    "neo": _neo_checks,
}


def analyze_lanes(
    bundle: dict[str, Any],
    *,
    target: str,
    lanes: Iterable[str],
    market: str | None = None,
    language: str | None = None,
    outcomes: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    if bundle.get("schema_version") != 1 or bundle.get("kind") != "EvidenceBundle":
        raise ValueError("lane analysis requires EvidenceBundle v1")
    selected = tuple(dict.fromkeys(lanes))
    unknown = set(selected) - set(ALL_LANES)
    if unknown:
        raise ValueError(f"unsupported lanes: {sorted(unknown)}")
    measured_at = str(bundle.get("collected_at") or _utc_now())
    inferred_language = language or bundle.get("content", {}).get("language")
    return {
        lane: build_lane_report(
            lane,
            target,
            _ANALYZERS[lane](bundle, target),
            outcomes=(outcomes or {}).get(lane, []),
            market=market,
            language=inferred_language,
            measured_at=measured_at,
        )
        for lane in selected
    }


def _load_bundle(path: Path) -> dict[str, Any]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("evidence bundle must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AutoSEO five-lane readiness engine")
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select", help="show automatically selected lanes")
    select.add_argument("target")
    select.add_argument("--market")
    select.add_argument("--language")
    select.add_argument("--request")
    select.add_argument("--all", action="store_true")
    audit = sub.add_parser("audit", help="analyze an EvidenceBundle or public URL")
    audit.add_argument("target")
    audit.add_argument("--bundle", type=Path)
    audit.add_argument("--lane", choices=("auto", "all", *ALL_LANES), default="auto")
    audit.add_argument("--market")
    audit.add_argument("--language")
    args = parser.parse_args(argv)

    try:
        if args.command == "select":
            lanes = select_lanes(
                args.target,
                market=args.market,
                language=args.language,
                request=args.request,
                run_all=args.all,
            )
            print(json.dumps({"schema_version": 1, "lanes": lanes}, indent=2))
            return 0

        if args.bundle:
            bundle = _load_bundle(args.bundle)
        elif _looks_like_url(args.target):
            with EvidenceEngine() as engine:
                bundle = engine.collect(args.target)
        else:
            raise ValueError("a URL or --bundle EvidenceBundle v1 is required")
        if args.lane == "all":
            lanes = ALL_LANES
        elif args.lane == "auto":
            lanes = select_lanes(
                args.target, market=args.market, language=args.language
            )
        else:
            lanes = (args.lane,)
        reports = analyze_lanes(
            bundle,
            target=args.target,
            lanes=lanes,
            market=args.market,
            language=args.language,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
