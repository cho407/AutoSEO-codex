#!/usr/bin/env python3
"""Collect public Google trend RSS and reviewed category research without provider credentials."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from file_safety import read_text_limited, write_text_safely
from korean_text import normalize_text
from trend_evidence import REFRESH_HOURS, WINDOW_HOURS, canonicalize_url
from url_safety import read_limited_response, safe_requests_session, validate_url

MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 100
RSS_URL = "https://trends.google.com/trending/rss?geo={}"


def _text(value: object, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    text = normalize_text(value)
    if len(text) > maximum or any(ord(c) < 32 for c in text):
        raise ValueError(f"{label} exceeds text limits")
    return text


def _date(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO 8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now(as_of: str | None) -> datetime:
    return _date(as_of) if as_of is not None else datetime.now(timezone.utc)


def _url(value: object) -> str:
    value = _text(value, "public URL", 2000)
    if not validate_url(value):
        raise ValueError("source must be a public HTTP(S) URL")
    return canonicalize_url(value)


@lru_cache(maxsize=1)
def category_catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "data" / "trend-categories.json"
    return json.loads(read_text_limited(path, max_bytes=MAX_BYTES, extensions={".json"}))


def resolve_categories(values: list[str] | None) -> list[str]:
    aliases = {"all": "all", "전체": "all"}
    for category in category_catalog()["categories"]:
        for name in [category["id"], category["label"], *category["aliases"]]:
            aliases[normalize_text(name).casefold()] = category["id"]
    resolved = []
    for raw in values or ["all"]:
        key = _text(raw, "category", 60).casefold()
        if key not in aliases:
            raise ValueError("unknown category; run categories or use --keyword for a custom topic")
        if aliases[key] not in resolved:
            resolved.append(aliases[key])
    if len(resolved) > 4 or ("all" in resolved and len(resolved) > 1):
        raise ValueError("select all alone or up to four categories per collection")
    return resolved


def _matches(text: str, term: str) -> bool:
    text, term = normalize_text(text).casefold(), normalize_text(term).casefold()
    # Do not classify 'chair' as AI; Korean compounds (제주여행) remain useful matches.
    if re.fullmatch(r"[a-z0-9 .-]+", term):
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None
    return term in text


def classify(text: str) -> list[dict[str, Any]]:
    result = []
    for category in category_catalog()["categories"]:
        matched = [term for term in category["terms"] if _matches(text, term)]
        if matched:
            result.append(
                {
                    "id": category["id"],
                    "label": category["label"],
                    "method": "keyword-rule-v1",
                    "matched_terms": matched,
                    "confidence": "heuristic",
                    "reason": "Matched keyword or linked-news headline",
                }
            )
    return result


def _categorization(keyword: str, context: str) -> tuple[list[dict], list[dict]]:
    categories = classify(keyword)
    direct_ids = {c["id"] for c in categories}
    hints = []
    for category in classify(context):
        if category["id"] not in direct_ids:
            category.update(
                method="headline-context-v1",
                confidence="review-required",
                reason="Context-only match; not used for category filtering without review",
            )
            hints.append(category)
    return categories, hints


def _scope(market, language, window, categories, keywords, exclude, limit) -> dict:
    if not isinstance(market, str) or not re.fullmatch(r"[A-Z]{2}", market):
        raise ValueError("market must be an uppercase two-letter country code")
    if not isinstance(language, str) or not re.fullmatch(
        r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", language
    ):
        raise ValueError("language must be a language code")
    if not isinstance(window, str) or window not in WINDOW_HOURS:
        raise ValueError("unsupported window")
    if type(limit) is not int or not 1 <= limit <= MAX_ITEMS:
        raise ValueError("limit must be an integer between 1 and 100")
    filters = {}
    for name, values in (("keywords", keywords), ("exclude", exclude)):
        if values is not None and (not isinstance(values, list) or len(values) > 10):
            raise ValueError(f"{name} must contain at most ten terms")
        filters[name] = list(dict.fromkeys(_text(v, name, 80) for v in values or []))
    return {
        "market": market,
        "language": language,
        "window": window,
        "categories": resolve_categories(categories),
        **filters,
        "limit": limit,
    }


def research_plan(
    *,
    market="KR",
    language="ko",
    window="24h",
    categories=None,
    keywords=None,
    exclude=None,
    limit=30,
    as_of=None,
) -> dict:
    scope = _scope(market, language, window, categories, keywords, exclude, limit)
    now = _now(as_of)
    # Search date filters are only a discovery hint; collection checks exact timestamps.
    after = (now - timedelta(hours=WINDOW_HOURS[window], days=1)).date().isoformat()
    labels = {row["id"]: row["label"] for row in category_catalog()["categories"]}
    queries = []
    for category in scope["categories"]:
        label = labels.get(category, "주요 이슈") if language.startswith("ko") else category
        topic = " ".join([label, *scope["keywords"]])
        location = "대한민국" if market == "KR" and language.startswith("ko") else market
        suffixes = (
            ["최신 발표 공식", "최근 소식"]
            if language.startswith("ko")
            else ["latest official announcement", "latest news"]
        )
        for suffix in suffixes:
            queries.append(
                {"category": category, "query": f"{location} {topic} {suffix} after:{after}"}
            )
    return {
        "schema_version": 1,
        "kind": "TrendResearchPlan",
        "status": "not-run",
        "created_at": now.isoformat(),
        "scope": scope,
        "queries": queries,
        "execution": "Run these bounded queries with Codex-native web search; inspect sources and record actual queries and dates as TrendResearch v1. This helper does not execute web search.",
    }


def fetch_google_trends(market: str) -> bytes:
    if not re.fullmatch(r"[A-Z]{2}", market):
        raise ValueError("invalid market")
    url = RSS_URL.format(market)
    with safe_requests_session(url) as session:
        session.trust_env = False  # No ambient .netrc credentials or authenticated proxies.
        session.auth = None
        session.cookies.clear()
        session.headers.clear()
        response = session.get(
            url,
            headers={
                "User-Agent": "AutoSEO public trend collector",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
            timeout=(5, 15),
            allow_redirects=False,
            stream=True,
        )
        if response.status_code != 200:
            response.close()
            raise ValueError("trend provider returned an unsupported HTTP status")
        return read_limited_response(response, max_bytes=MAX_BYTES).content


def parse_google_rss(content: bytes) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise ValueError("RSS exceeds the size limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("RSS must be UTF-8") from exc
    if "\x00" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)", text, re.I):
        raise ValueError("DTD and entities are not supported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("invalid RSS XML") from exc
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("expected a public RSS channel, not a login or error page")
    items = root.findall("./channel/item")
    if len(items) > 500:
        raise ValueError("RSS contains too many items")

    def field(element, name):
        child = next((x for x in element if x.tag.rsplit("}", 1)[-1] == name), None)
        return "" if child is None else "".join(child.itertext()).strip()

    result = []
    for position, item in enumerate(items, 1):
        news = []
        for child in item:
            if child.tag.rsplit("}", 1)[-1] != "news_item" or len(news) >= 3:
                continue
            try:
                news.append(
                    {
                        "title": _text(html.unescape(field(child, "news_item_title")), "headline"),
                        "url": _url(field(child, "news_item_url")),
                    }
                )
            except ValueError:
                continue
        result.append(
            {
                "keyword": html.unescape(field(item, "title")),
                "date": field(item, "pubDate"),
                "traffic_bucket": field(item, "approx_traffic"),
                "related_news": news,
                "source_position": position,
            }
        )
    return result


def _check_fields(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{label} must be an object with supported fields only")
    return value


def _research(value: object, scope: dict, now: datetime) -> tuple[list[dict], list[dict]]:
    value = _check_fields(
        value,
        {"schema_version", "kind", "market", "language", "window", "queries", "observations"},
        "research",
    )
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("kind") != "TrendResearch"
    ):
        raise ValueError("expected TrendResearch v1")
    if any(value.get(key) != scope[key] for key in ("market", "language", "window")):
        raise ValueError("research scope must match collection market, language and window")
    queries, observations = value.get("queries"), value.get("observations")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 8:
        raise ValueError("record between one and eight executed queries")
    if not isinstance(observations, list) or len(observations) > MAX_ITEMS:
        raise ValueError("research supports at most 100 observations")
    ledger = {}
    clean_queries = []
    for raw in queries:
        row = _check_fields(raw, {"query", "searched_at", "urls"}, "query")
        query = _text(row.get("query"), "query")
        searched = _date(row.get("searched_at"))
        if query in ledger or searched > now + timedelta(minutes=5):
            raise ValueError("queries must be unique and not future dated")
        urls = row.get("urls")
        if not isinstance(urls, list) or len(urls) > 20:
            raise ValueError("a query supports at most 20 inspected URLs")
        ledger[query] = {"urls": {_url(url) for url in urls}, "searched_at": searched}
        clean_queries.append(
            {
                "query": query,
                "searched_at": searched.isoformat(),
                "urls": sorted(ledger[query]["urls"]),
            }
        )
    result = []
    labels = {row["id"]: row["label"] for row in category_catalog()["categories"]}
    for raw in observations:
        row = _check_fields(
            raw,
            {
                "keyword",
                "title",
                "url",
                "source_type",
                "published_at",
                "published_precision",
                "observed_at",
                "query",
                "categories",
                "category_reason",
            },
            "observation",
        )
        keyword = _text(row.get("keyword"), "keyword", 200)
        title = _text(row.get("title"), "title")
        url = _url(row.get("url"))
        query = _text(row.get("query"), "query")
        if query not in ledger or url not in ledger[query]["urls"]:
            raise ValueError("observation must reference an inspected query URL")
        if row.get("source_type") not in ("primary-source", "news"):
            raise ValueError("research observations require dated primary sources or news")
        published, observed = _date(row.get("published_at")), _date(row.get("observed_at"))
        precision = row.get("published_precision", "timestamp")
        if precision not in ("day", "timestamp"):
            raise ValueError("published_precision must be day or timestamp")
        if (
            observed > now + timedelta(minutes=5)
            or published > observed + timedelta(minutes=5)
            or observed < ledger[query]["searched_at"]
        ):
            raise ValueError("research timestamps are inconsistent or future dated")
        assigned = row.get("categories", [])
        if (
            not isinstance(assigned, list)
            or len(assigned) > 4
            or any(not isinstance(x, str) or x not in labels for x in assigned)
        ):
            raise ValueError("reviewed categories must use up to four catalog IDs")
        categories, hints = _categorization(keyword, title)
        if assigned:
            reason = _text(row.get("category_reason"), "category_reason", 300)
            categories = [c for c in categories if c["id"] not in assigned]
            hints = [c for c in hints if c["id"] not in assigned]
            categories.extend(
                {
                    "id": c,
                    "label": labels[c],
                    "method": "reviewed-category",
                    "matched_terms": [],
                    "confidence": "review-required",
                    "reason": reason,
                }
                for c in dict.fromkeys(assigned)
            )
        result.append(
            {
                "keyword": keyword,
                "categories": categories,
                "category_hints": hints,
                "text": f"{keyword} {title}",
                "timestamp": published,
                "observed": observed,
                "evidence": {
                    "source_type": row["source_type"],
                    "source": urlsplit(url).hostname,
                    "method": "codex-web-reviewed-v1",
                    "url": url,
                    "title": title,
                    "published_at": published.isoformat(),
                    "published_precision": precision,
                    "observed_at": observed.isoformat(),
                    "query": query,
                    "traffic_bucket": None,
                },
            }
        )
    return result, clean_queries


def collect_trends(
    *,
    market="KR",
    language="ko",
    window="24h",
    categories=None,
    keywords=None,
    exclude=None,
    limit=30,
    rss_content=None,
    research=None,
    fetcher=None,
    as_of=None,
) -> dict:
    scope = _scope(market, language, window, categories, keywords, exclude, limit)
    now = _now(as_of)
    records, queries = _research(research, scope, now) if research is not None else ([], [])
    research_count = len(records)
    source = {
        "id": "google-trends-trending-now",
        "url": RSS_URL.format(market),
        "access": "public-no-login",
        "status": "collected",
        "retrieved_at": now.isoformat(),
        "mode": "supplied-rss" if rss_content is not None else "live-rss",
    }
    excluded = {"stale": 0, "future": 0, "invalid": 0}
    try:
        feed = parse_google_rss(
            rss_content if rss_content is not None else (fetcher or fetch_google_trends)(market)
        )
    except (requests.RequestException, OSError, ValueError):
        if rss_content is not None:
            raise  # Invalid local inputs are caller errors, not a provider outage.
        feed = []
        source.update(
            status="unavailable",
            reason="Fetch failed, unsupported response, or invalid RSS; no credential or response details retained.",
        )
    for row in feed:
        try:
            keyword = _text(row["keyword"], "keyword", 200)
            published = parsedate_to_datetime(row["date"])
            if published.tzinfo is None:
                raise ValueError("RSS date has no timezone")
            published = published.astimezone(timezone.utc)
            text = " ".join([keyword, *(x["title"] for x in row["related_news"])])
            assigned, hints = _categorization(keyword, text)
            bucket = row["traffic_bucket"]
            bucket = (
                bucket
                if re.fullmatch(r"[0-9,.]+[KMBkmb]?\+?", bucket) and len(bucket) <= 30
                else None
            )
            records.append(
                {
                    "keyword": keyword,
                    "categories": assigned,
                    "category_hints": hints,
                    "text": text,
                    "timestamp": published,
                    "observed": now,
                    "evidence": {
                        "source_type": "official-trend",
                        "source": "google-trends",
                        "method": "google-trending-rss-v1",
                        "url": source["url"],
                        "title": keyword,
                        "feed_published_at": published.isoformat(),
                        "observed_at": now.isoformat(),
                        "traffic_bucket": bucket,
                        "source_position": row["source_position"],
                        "related_news": row["related_news"],
                    },
                }
            )
        except (TypeError, ValueError, OverflowError):
            excluded["invalid"] += 1
    candidates = {}
    seen = set()
    duplicates = 0
    cutoff = now - timedelta(hours=WINDOW_HOURS[window])
    records.sort(key=lambda row: (row["timestamp"], row["observed"]), reverse=True)
    for row in records:
        if row["timestamp"] > now + timedelta(minutes=5):
            excluded["future"] += 1
            continue
        if row["timestamp"] < cutoff or row["observed"] < cutoff:
            excluded["stale"] += 1
            continue
        key = normalize_text(row["keyword"]).casefold()
        identity = (key, row["evidence"]["method"], row["evidence"]["url"])
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        item = candidates.setdefault(
            key,
            {
                "id": hashlib.sha256(f"{market}:{language}:{key}".encode()).hexdigest()[:16],
                "keyword": row["keyword"],
                "categories": [],
                "category_hints": [],
                "evidence": [],
                "newest_at": row["timestamp"].isoformat(),
                "exact_search_volume": None,
                "demand_status": "unmeasured",
                "next_action": "verify-event-and-demand-before-brief",
                "_text": "",
            },
        )
        # A reviewed category assignment takes precedence over the local heuristic.
        by_id = {c["id"]: c for c in row["categories"]}
        for old in item["categories"]:
            if old["id"] not in by_id or old["method"] == "reviewed-category":
                by_id[old["id"]] = old
        item["categories"] = list(by_id.values())
        hints = {c["id"]: c for c in [*item["category_hints"], *row["category_hints"]]}
        item["category_hints"] = [c for key, c in hints.items() if key not in by_id]
        item["evidence"].append(row["evidence"])
        item["_text"] += " " + row["text"]
        item["newest_at"] = max(item["newest_at"], row["timestamp"].isoformat())
        if row["evidence"]["source_type"] == "official-trend":
            item["demand_status"] = "observed-surge-single-provider"
    matched = []
    for item in candidates.values():
        text = item.pop("_text")
        category_ids = {x["id"] for x in item["categories"]}
        if scope["categories"] != ["all"] and not category_ids.intersection(scope["categories"]):
            continue
        if scope["keywords"] and not any(_matches(text, word) for word in scope["keywords"]):
            continue
        if any(_matches(text, word) for word in scope["exclude"]):
            continue
        matched.append(item)
    matched.sort(key=lambda item: (item["newest_at"], item["keyword"]), reverse=True)
    items = matched[:limit]
    group_catalog = [*category_catalog()["categories"], {"id": "uncategorized", "label": "미분류"}]
    groups = []
    for group in group_catalog:
        if scope["categories"] != ["all"] and group["id"] not in scope["categories"]:
            continue
        ids = [
            x["id"]
            for x in items
            if group["id"] in ({c["id"] for c in x["categories"]} or {"uncategorized"})
        ]
        groups.append(
            {"id": group["id"], "label": group["label"], "count": len(ids), "item_ids": ids}
        )
    refresh_delta = timedelta(hours=REFRESH_HOURS[window])
    query_expiries = [_date(q["searched_at"]) + refresh_delta for q in queries]
    recent_queries = sum(expiry > now for expiry in query_expiries)
    research_stale = recent_queries < len(queries)
    refresh_after = min([now + refresh_delta, *query_expiries])
    if source["status"] == "collected":
        status = "partial" if research_stale else "ok"
    else:
        status = "partial" if recent_queries else "unavailable"
    return {
        "schema_version": 1,
        "kind": "TrendCollection",
        "scope": scope,
        "collected_at": now.isoformat(),
        "refresh_after": refresh_after.isoformat(),
        "status": status,
        "sources": [source],
        "items": items,
        "groups": groups,
        "research_queries": queries,
        "counts": {
            "feed_items": len(feed),
            "research_observations": research_count,
            "duplicate_observations": duplicates,
            "excluded": excluded,
            "fresh_candidates": len(candidates),
            "needs_category_review": sum(bool(x["category_hints"]) for x in candidates.values()),
            "matched": len(matched),
            "returned": len(items),
            "truncated": len(matched) > limit,
        },
        "coverage": {
            "exhaustive": False,
            "category_method": "local-keyword-rules-and-reviewed-evidence",
            "research_status": "stale" if research_stale else "collected" if queries else "not-run",
            "query_count": len(queries),
            "recent_query_count": recent_queries,
            "ordering": "newest evidence first, not a demand or search ranking",
        },
        "research_plan": research_plan(**scope, as_of=now.isoformat()),
        "limitations": [
            "The RSS feed is a limited current snapshot, not all market or category trends. A wider window does not backfill missing history.",
            "Google reports Trending Now refreshes about every ten minutes; RSS delivery has no guaranteed latency here.",
            "Categories are AutoSEO editorial inferences, not provider-certified categories. An empty category does not prove zero demand.",
            "Google RSS is market-scoped, not language-filtered. Requested language guides research; it does not measure every source's language.",
            "Traffic buckets are not exact query counts. News discovery, search surge and relative interest are different signals.",
            "Linked RSS headlines are discovery context, not inspected articles or independently verified facts. Research query URLs are user/agent observations.",
            "No promise of ranking, clicks or future demand; corroborate original events before writing. No scheduled execution or publishing is enabled.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("categories")
    for command in ("plan", "collect"):
        child = sub.add_parser(command)
        child.add_argument("--market", default="KR")
        child.add_argument("--language", default="ko")
        child.add_argument("--window", choices=sorted(WINDOW_HOURS), default="24h")
        child.add_argument("--category", action="append", dest="categories")
        child.add_argument("--keyword", action="append", dest="keywords")
        child.add_argument("--exclude", action="append")
        child.add_argument("--limit", type=int, default=30)
        child.add_argument(
            "--as-of", help="Explicit evaluation time for reproducible snapshots; omit for live use"
        )
        child.add_argument("--output", type=Path)
        child.add_argument("--overwrite", action="store_true")
        if command == "collect":
            child.add_argument(
                "--rss-file",
                type=Path,
                help="Supplied Google RSS snapshot; disables the HTTP fetch",
            )
            child.add_argument(
                "--research-input",
                type=Path,
                help="Dated TrendResearch v1 observations from native web research",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "categories":
            result = category_catalog()
        else:
            kwargs = {
                name: getattr(args, name)
                for name in (
                    "market",
                    "language",
                    "window",
                    "categories",
                    "keywords",
                    "exclude",
                    "limit",
                    "as_of",
                )
            }
            if args.command == "plan":
                result = research_plan(**kwargs)
            else:
                feed = (
                    read_text_limited(
                        args.rss_file, max_bytes=MAX_BYTES, extensions={".xml", ".rss"}
                    ).encode()
                    if args.rss_file
                    else None
                )
                research = (
                    json.loads(
                        read_text_limited(
                            args.research_input, max_bytes=MAX_BYTES, extensions={".json"}
                        )
                    )
                    if args.research_input
                    else None
                )
                result = collect_trends(**kwargs, rss_content=feed, research=research)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if getattr(args, "output", None):
            write_text_safely(args.output, rendered, overwrite=args.overwrite, extensions={".json"})
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(rendered, end="")
    return 0 if result.get("status") != "unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
