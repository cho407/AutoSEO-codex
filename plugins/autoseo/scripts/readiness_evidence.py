"""Conservative dated evidence; never infer meaning from link counts."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

RULE_VERSION = "2026-09-07.1"


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps require a timezone")
    return parsed.astimezone(timezone.utc)


def directives(bundle: dict, crawler: str = "googlebot") -> set[str]:
    """Keep crawler-scoped HTTP directives separate from general directives."""
    metadata = bundle.get("metadata", {})
    values = [str(metadata.get("meta_robots") or "")]
    values.extend(str(value) for name, value in metadata.get("robots_by_agent", {}).items()
                  if name.casefold() == crawler.casefold())
    for name, value in bundle.get("source_response", {}).get("headers", {}).items():
        if name.casefold() != "x-robots-tag":
            continue
        agent = None
        for part in str(value).casefold().split(","):
            part = part.strip()
            match = re.match(r"^([\w-]+):\s*(.*)$", part)
            if match and match[1] not in {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}:
                agent, part = match.groups()
            if agent is None or agent == crawler.casefold():
                values.append(part)
    return {re.sub(r"\s*:\s*", ":", token.strip().casefold())
            for value in values for token in value.split(",") if token.strip()}


def canonical_status(bundle: dict) -> tuple[str, dict]:
    source = bundle.get("url") or bundle.get("requested_url") or ""
    value = bundle.get("metadata", {}).get("canonical")
    resolved = urljoin(source, value) if isinstance(value, str) else None
    evidence = {"page_url": source, "canonical_url": resolved}
    if not value:
        return "fail", evidence
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return "fail", evidence

    def key(url: str) -> tuple:
        part = urlsplit(url)
        return part.scheme.lower(), part.netloc.lower(), part.path or "/", part.query

    if key(source) == key(resolved):
        return "pass", evidence
    evidence["limitation"] = "Alternate canonical may be intentional; verify the representative URL and consolidation intent."
    return "unmeasured", evidence


def dated_site_signal(bundle: dict, name: str) -> tuple[str, list]:
    """Accept observations only for this origin, page and capture window."""
    site = bundle.get("site_evidence", {})
    if not isinstance(site, dict):
        return "unmeasured", []
    source = urlsplit(bundle.get("url", ""))
    origin = urlunsplit((source.scheme, source.netloc, "", "", ""))
    try:
        age = (timestamp(bundle["collected_at"]) - timestamp(site["observed_at"])).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        return "unmeasured", []
    if site.get("origin") != origin or site.get("page_url") != bundle.get("url") or not 0 <= age <= 86400:
        return "unmeasured", []
    checks = site.get("checks", {})
    if not isinstance(checks, dict):
        return "unmeasured", []
    signal = checks.get(name)
    if not isinstance(signal, dict) or not isinstance(signal.get("allowed"), bool):
        return "unmeasured", []
    evidence_url = signal.get("url")
    if not isinstance(evidence_url, str) or urlsplit(evidence_url).netloc != source.netloc:
        return "unmeasured", []
    if not isinstance(signal.get("detail"), str) or not signal["detail"].strip():
        return "unmeasured", []
    return ("pass" if signal["allowed"] else "fail"), [
        {**signal, "observed_at": site["observed_at"], "origin": origin}
    ]


def semantic_review(bundle: dict, name: str) -> tuple[str, list]:
    """Check explicit review provenance, not whether the judgment itself is true."""
    reviews = bundle.get("review_evidence", {})
    if not isinstance(reviews, dict):
        return "unmeasured", []
    review = reviews.get(name)
    if not isinstance(review, dict) or review.get("status") not in {"pass", "fail"}:
        return "unmeasured", []
    quote = review.get("excerpt")
    if (
        review.get("page_url") != bundle.get("url")
        or review.get("collected_at") != bundle.get("collected_at")
        or not isinstance(quote, str) or not quote.strip()
        or quote not in bundle.get("content", {}).get("text", "")
        or not isinstance(review.get("reason"), str) or not review["reason"].strip()
        or review.get("reviewer") not in {"user", "codex"}
    ):
        return "unmeasured", []
    try:
        if not timestamp(bundle["collected_at"]) <= timestamp(review["reviewed_at"]) <= datetime.now(timezone.utc):
            return "unmeasured", []
    except (KeyError, ValueError, TypeError, AttributeError):
        return "unmeasured", []
    if name in {"claim_source_support", "source_support", "external_corroboration", "authorship"}:
        sources = review.get("sources")
        if not isinstance(sources, list) or not sources:
            return "unmeasured", []
        for item in sources:
            if not isinstance(item, dict) or not item.get("excerpt") or not item.get("relation"):
                return "unmeasured", []
            url = urlsplit(str(item.get("url", "")))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username:
                return "unmeasured", []
    return review["status"], [review]
