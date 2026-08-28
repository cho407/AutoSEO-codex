#!/usr/bin/env python3
"""Query public RDAP registration data through a bounded HTTPS bootstrap flow."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from requests import RequestException
from url_safety import URLSafetyError, safe_requests_get

BOOTSTRAP_ORIGIN = "https://rdap.org"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 4
DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalize_domain(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("domain is required")
    domain = value.strip().lower().rstrip(".")
    if "://" in domain or "/" in domain or "\\" in domain or "@" in domain:
        raise ValueError("enter a domain name without a URL, path, or credentials")
    try:
        domain = domain.encode("idna").decode("ascii")
        ipaddress.ip_address(domain)
    except UnicodeError as exc:
        raise ValueError("domain cannot be encoded as IDNA") from exc
    except ValueError:
        pass
    else:
        raise ValueError("RDAP domain lookup does not accept IP addresses")
    labels = domain.split(".")
    if (
        len(labels) < 2
        or len(domain) > 253
        or any(not DOMAIN_LABEL_RE.fullmatch(label) for label in labels)
    ):
        raise ValueError("invalid domain name")
    return domain


def _bootstrap_url(domain: str) -> str:
    return f"{BOOTSTRAP_ORIGIN}/domain/{quote(_normalize_domain(domain), safe='.-')}"


def _safe_redirect(current: str, location: str) -> str:
    target = urljoin(current, location)
    parsed = urlparse(target)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.fragment
    ):
        raise ValueError("RDAP redirect must be a plain public HTTPS URL")
    return target


def _fetch(domain: str) -> dict[str, Any]:
    url = _bootstrap_url(domain)
    headers = {"Accept": "application/rdap+json, application/json", "User-Agent": "AutoSEO/0.3"}
    for _ in range(MAX_REDIRECTS + 1):
        response = safe_requests_get(
            url,
            timeout=20,
            max_response_bytes=MAX_RESPONSE_BYTES,
            allow_redirects=False,
            headers=headers,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            if not location:
                raise ValueError("RDAP redirect omitted Location")
            url = _safe_redirect(url, location)
            continue
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("RDAP response must be a JSON object")
        return value
    raise ValueError("RDAP redirect limit exceeded")


def _event_map(events: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(events, list):
        return result
    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("eventAction")
        date = event.get("eventDate")
        if isinstance(action, str) and isinstance(date, str):
            result[action] = date
    return result


def _entity_summary(entities: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(entities, list):
        return result
    for entity in entities[:50]:
        if not isinstance(entity, dict):
            continue
        roles = entity.get("roles")
        result.append(
            {
                "handle": entity.get("handle") if isinstance(entity.get("handle"), str) else None,
                "roles": [role for role in roles if isinstance(role, str)] if isinstance(roles, list) else [],
            }
        )
    return result


def lookup(domain: str) -> dict[str, Any]:
    normalized = _normalize_domain(domain)
    raw = _fetch(normalized)
    nameservers = []
    for item in raw.get("nameservers", []) if isinstance(raw.get("nameservers"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("ldhName"), str):
            nameservers.append(item["ldhName"].lower())
    return {
        "schema_version": 1,
        "source": "rdap",
        "domain": normalized,
        "handle": raw.get("handle") if isinstance(raw.get("handle"), str) else None,
        "status": [item for item in raw.get("status", []) if isinstance(item, str)]
        if isinstance(raw.get("status"), list)
        else [],
        "events": _event_map(raw.get("events")),
        "nameservers": sorted(set(nameservers)),
        "entities": _entity_summary(raw.get("entities")),
        "notices": [
            item.get("title")
            for item in raw.get("notices", [])
            if isinstance(item, dict) and isinstance(item.get("title"), str)
        ]
        if isinstance(raw.get("notices"), list)
        else [],
        "limitations": [
            "Registries may redact registration fields.",
            "Registration age or status is not a search-authority score.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = lookup(args.domain)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RequestException, URLSafetyError) as exc:
        print(f"RDAP lookup error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
