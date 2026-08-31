#!/usr/bin/env python3
"""Optional no-subscription Naver Search, DataLab, and AI Briefing evidence."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from file_safety import read_text_limited
from korean_text import normalize_text
from url_safety import (
    read_limited_response,
    safe_requests_get,
    safe_requests_session,
    validate_url,
)

SCHEMA_VERSION = 1
LEGACY_SEARCH_ENDPOINTS = {
    "blog": "https://openapi.naver.com/v1/search/blog.json",
    "webkr": "https://openapi.naver.com/v1/search/webkr.json",
    "kin": "https://openapi.naver.com/v1/search/kin.json",
    "cafearticle": "https://openapi.naver.com/v1/search/cafearticle.json",
    "local": "https://openapi.naver.com/v1/search/local.json",
}
API_HUB_SEARCH_ENDPOINTS = {
    vertical: f"https://naverapihub.apigw.ntruss.com/search/v1/{vertical}"
    for vertical in LEGACY_SEARCH_ENDPOINTS
}
SEARCH_ENDPOINTS = LEGACY_SEARCH_ENDPOINTS
SEARCH_SORTS = {
    "blog": {"sim", "date"},
    "webkr": {"sim", "date"},
    "kin": {"sim", "date", "point"},
    "cafearticle": {"sim", "date"},
    "local": {"random", "comment"},
}
LEGACY_DATALAB_ENDPOINT = "https://openapi.naver.com/v1/datalab/search"
API_HUB_DATALAB_ENDPOINT = (
    "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
)
DATALAB_ENDPOINT = LEGACY_DATALAB_ENDPOINT
PROVIDERS = {"legacy", "api-hub-free"}
LEGACY_SUPPORT_END = "2027-06-30"
AI_BRIEFING_SURFACES = {
    "official",
    "multi-source",
    "blog",
    "place",
    "shopping",
    "short-content",
    "not-observed",
}
MAX_AI_BRIEFING_SAMPLES = 25
MAX_AI_BRIEFING_SOURCES = 50
_TAG_RE = re.compile(r"<[^>]+>")


def _captured_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_config(provider: str) -> tuple[dict[str, str], str, str]:
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of: {sorted(PROVIDERS)}")
    if provider == "api-hub-free":
        if os.environ.get("AUTOSEO_CONFIRM_NAVER_API_HUB_NO_BILLING") != "1":
            raise ValueError(
                "api-hub-free requires explicit no-billing confirmation through "
                "AUTOSEO_CONFIRM_NAVER_API_HUB_NO_BILLING=1; AutoSEO will not "
                "assume a temporarily free account cannot incur future charges"
            )
        client_id = os.environ.get("NAVER_API_HUB_CLIENT_ID")
        client_secret = os.environ.get("NAVER_API_HUB_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError(
                "NAVER_API_HUB_CLIENT_ID and NAVER_API_HUB_CLIENT_SECRET "
                "environment variables are required"
            )
        return (
            {
                "X-NCP-APIGW-API-KEY-ID": client_id,
                "X-NCP-APIGW-API-KEY": client_secret,
            },
            "api-hub-free-confirmed",
            "caller-confirmed-no-billing",
        )
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError(
            "NAVER_CLIENT_ID and NAVER_CLIENT_SECRET environment variables are required"
        )
    return (
        {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
        "developers-legacy",
        "legacy-key-only-until-2027-06-30",
    )


def _query(value: str) -> str:
    normalized = normalize_text(value)
    if not normalized or len(normalized) > 200:
        raise ValueError("query must contain between 1 and 200 characters")
    return normalized


def _clean_text(value: object) -> str:
    return normalize_text(html.unescape(_TAG_RE.sub("", str(value or ""))))


def search(
    query: str,
    *,
    vertical: str = "blog",
    display: int | None = None,
    start: int = 1,
    sort: str | None = None,
    provider: str = "legacy",
    request_get: Callable[..., Any] = safe_requests_get,
) -> dict[str, Any]:
    """Read one free Naver Search API vertical without persisting credentials."""
    if vertical not in SEARCH_ENDPOINTS:
        raise ValueError(f"vertical must be one of: {sorted(SEARCH_ENDPOINTS)}")
    if display is None:
        display = 1 if vertical == "local" else 10
    maximum_display = 5 if vertical == "local" else 100
    if not 1 <= display <= maximum_display:
        raise ValueError(f"display must be between 1 and {maximum_display}")
    if vertical == "local" and start != 1:
        raise ValueError("local search start must be 1")
    if vertical != "local" and not 1 <= start <= 1_000:
        raise ValueError("start must be between 1 and 1000")
    sort = sort or ("random" if vertical == "local" else "sim")
    if sort not in SEARCH_SORTS[vertical]:
        raise ValueError(f"sort for {vertical} must be one of: {sorted(SEARCH_SORTS[vertical])}")
    normalized_query = _query(query)
    headers, provider_label, cost_guard = _provider_config(provider)
    endpoints = (
        API_HUB_SEARCH_ENDPOINTS if provider == "api-hub-free" else LEGACY_SEARCH_ENDPOINTS
    )
    response = request_get(
        endpoints[vertical],
        headers=headers,
        params={
            "query": normalized_query,
            "display": display,
            "start": start,
            "sort": sort,
        },
        timeout=20,
        max_response_bytes=2 * 1024 * 1024,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("items", []), list):
        raise ValueError("Naver Search returned an unexpected response")
    items: list[dict[str, Any]] = []
    for position, item in enumerate(payload.get("items", [])[:display], start=start):
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        items.append(
            {
                "position": position,
                "title": _clean_text(item.get("title")),
                "description": _clean_text(item.get("description")),
                "url": link if isinstance(link, str) and validate_url(link) else None,
                "blogger_name": _clean_text(item.get("bloggername")) or None,
                "post_date": _clean_text(item.get("postdate")) or None,
                "category": _clean_text(item.get("category")) or None,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "NaverSearchEvidence",
        "query": normalized_query,
        "vertical": vertical,
        "captured_at": _captured_at(),
        "market": "KR",
        "language": "ko",
        "total": payload.get("total"),
        "start": payload.get("start", start),
        "display": len(items),
        "provider": provider_label,
        "cost_guard": cost_guard,
        "legacy_support_end": LEGACY_SUPPORT_END if provider == "legacy" else None,
        "items": items,
        "subscription_required": False,
        "exact_search_volume": None,
        "limitations": [
            "Results are a dated API sample and may differ from personalized Naver Search.",
            "The API response does not prove indexing, ranking stability, or AI Briefing citation.",
            "NAVER API HUB is used only after the caller confirms the configured account has no billing path.",
        ],
    }


def _keyword_groups(value: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = list(value)
    if not 1 <= len(groups) <= 5:
        raise ValueError("DataLab requires between 1 and 5 keyword groups")
    normalized: list[dict[str, Any]] = []
    for group in groups:
        title = _query(str(group.get("groupName") or ""))
        keywords = group.get("keywords")
        if not isinstance(keywords, list) or not 1 <= len(keywords) <= 20:
            raise ValueError("each DataLab group requires between 1 and 20 keywords")
        normalized.append(
            {"groupName": title, "keywords": [_query(str(item)) for item in keywords]}
        )
    return normalized


def datalab_search(
    keyword_groups: Iterable[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
    time_unit: str = "date",
    device: str | None = None,
    gender: str | None = None,
    ages: list[str] | None = None,
    provider: str = "legacy",
    request_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read free relative Naver query trends; values are not exact volume."""
    try:
        start_value = date.fromisoformat(start_date)
        end_value = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("DataLab dates must use YYYY-MM-DD") from exc
    if start_value > end_value:
        raise ValueError("DataLab start_date must not be after end_date")
    if time_unit not in {"date", "week", "month"}:
        raise ValueError("time_unit must be date, week, or month")
    payload: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": _keyword_groups(keyword_groups),
    }
    if device:
        payload["device"] = device
    if gender:
        payload["gender"] = gender
    if ages:
        payload["ages"] = ages

    headers, provider_label, cost_guard = _provider_config(provider)
    endpoint = (
        API_HUB_DATALAB_ENDPOINT if provider == "api-hub-free" else LEGACY_DATALAB_ENDPOINT
    )
    if request_post is None:
        with safe_requests_session(endpoint) as session:
            response = session.post(
                endpoint,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
                timeout=20,
                stream=True,
            )
            response = read_limited_response(response, max_bytes=2 * 1024 * 1024)
    else:
        response = request_post(
            endpoint,
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict) or not isinstance(value.get("results", []), list):
        raise ValueError("Naver DataLab returned an unexpected response")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "NaverDataLabEvidence",
        "captured_at": _captured_at(),
        "market": "KR",
        "language": "ko",
        "period": {"start": start_date, "end": end_date, "unit": time_unit},
        "results": value.get("results", []),
        "provider": provider_label,
        "cost_guard": cost_guard,
        "legacy_support_end": LEGACY_SUPPORT_END if provider == "legacy" else None,
        "subscription_required": False,
        "exact_search_volume": None,
        "limitations": [
            "DataLab values are normalized relative trends, not exact search volume.",
            "Compare cohorts only when periods, filters, and keyword groups match.",
            "API HUB is used only after the caller confirms the configured account has no billing path.",
        ],
    }


def _validate_ai_briefing_sample(sample: dict[str, Any]) -> None:
    if sample.get("schema_version") != 1:
        raise ValueError("AI Briefing sample schema_version must be 1")
    _query(str(sample.get("query") or ""))
    if sample.get("surface") not in AI_BRIEFING_SURFACES:
        raise ValueError(f"AI Briefing surface must be one of: {sorted(AI_BRIEFING_SURFACES)}")
    if not isinstance(sample.get("observed"), bool):
        raise ValueError("AI Briefing observed must be boolean")
    sources = sample.get("sources", [])
    if not isinstance(sources, list) or len(sources) > MAX_AI_BRIEFING_SOURCES:
        raise ValueError(f"AI Briefing sources must contain at most {MAX_AI_BRIEFING_SOURCES} entries")
    for source in sources:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("url"), str)
            or not validate_url(source["url"])
            or not isinstance(source.get("target"), bool)
        ):
            raise ValueError("each AI Briefing source requires a public URL and target boolean")
    for field in ("market", "language", "captured_at"):
        if not isinstance(sample.get(field), str) or not sample[field].strip():
            raise ValueError(f"AI Briefing {field} is required")


def summarize_ai_briefing_samples(
    samples: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    values = list(samples)
    if not 1 <= len(values) <= MAX_AI_BRIEFING_SAMPLES:
        raise ValueError(
            f"AI Briefing sample count must be between 1 and {MAX_AI_BRIEFING_SAMPLES}"
        )
    observations: list[dict[str, Any]] = []
    for sample in values:
        _validate_ai_briefing_sample(sample)
        sources = sample.get("sources", [])
        observations.append(
            {
                "metric": "target_source_share",
                "query": normalize_text(sample["query"]),
                "observed": sample["observed"],
                "numerator": sum(bool(item["target"]) for item in sources),
                "denominator": len(sources),
                "market": sample["market"],
                "language": sample["language"],
                "surface": sample["surface"],
                "measured_at": sample["captured_at"],
                "confidence": "medium" if sample["observed"] and sources else "low",
                "limitations": [
                    "Small reproducible query sample; not platform-wide visibility.",
                    "Personalization, device, location, and time can change the result.",
                ],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "NaverAIBriefingObservations",
        "sample_count": len(values),
        "observations": observations,
        "guarantee": None,
    }


def _load_json(path: Path) -> Any:
    return json.loads(read_text_limited(path, extensions={".json"}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    search_parser = sub.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--vertical", choices=tuple(SEARCH_ENDPOINTS), default="blog")
    search_parser.add_argument("--display", type=int)
    search_parser.add_argument("--provider", choices=tuple(sorted(PROVIDERS)), default="legacy")
    trend_parser = sub.add_parser("datalab")
    trend_parser.add_argument("input", type=Path, help="JSON keyword group list")
    trend_parser.add_argument("--start-date", required=True)
    trend_parser.add_argument("--end-date", required=True)
    trend_parser.add_argument("--time-unit", choices=("date", "week", "month"), default="date")
    trend_parser.add_argument("--provider", choices=tuple(sorted(PROVIDERS)), default="legacy")
    briefing_parser = sub.add_parser("ai-briefing")
    briefing_parser.add_argument("input", type=Path, help="JSON sample list")
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            result = search(
                args.query,
                vertical=args.vertical,
                display=args.display,
                provider=args.provider,
            )
        elif args.command == "datalab":
            groups = _load_json(args.input)
            if not isinstance(groups, list):
                raise ValueError("DataLab input must be a JSON list")
            result = datalab_search(
                groups,
                start_date=args.start_date,
                end_date=args.end_date,
                time_unit=args.time_unit,
                provider=args.provider,
            )
        else:
            samples = _load_json(args.input)
            if not isinstance(samples, list):
                raise ValueError("AI Briefing input must be a JSON list")
            result = summarize_ai_briefing_samples(samples)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
