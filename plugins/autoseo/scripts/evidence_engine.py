#!/usr/bin/env python3
"""Collect one bounded, reusable evidence bundle per public URL."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from file_safety import write_text_atomically
from parse_html import parse_html
from render_page import RenderSession, _extract_json_ld, _is_spa
from url_safety import validate_url

SCHEMA_VERSION = 1
DEFAULT_BODY_CHARS = 16_000
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_GLOBAL_WORKERS = 4
DEFAULT_HOST_WORKERS = 2
MAX_LINKS_PER_KIND = 2_000
MAX_ENTITIES = 100

_SAFE_RESPONSE_HEADERS = {
    "cache-control",
    "content-language",
    "content-length",
    "content-type",
    "etag",
    "last-modified",
    "x-robots-tag",
}
_PRIVATE_PATH_PARTS = {"account", "admin", "auth", "login", "signin", "user"}

FetchResult = dict[str, Any]
Fetcher = Callable[[str], FetchResult]
RendererFactory = Callable[[], Any]


def _canonical_url(raw_url: str) -> str:
    value = raw_url.strip()
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    if not validate_url(value) or not parts.hostname:
        raise ValueError("URL must be a public HTTP(S) URL")
    hostname = parts.hostname.encode("idna").decode("ascii").lower()
    port = parts.port
    default_port = (parts.scheme == "https" and port == 443) or (
        parts.scheme == "http" and port == 80
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def build_fetch_waves(
    urls: Iterable[str],
    *,
    max_workers: int = DEFAULT_GLOBAL_WORKERS,
    per_host: int = DEFAULT_HOST_WORKERS,
) -> list[list[str]]:
    """Build order-preserving process waves with global and host bounds."""
    if max_workers < 1 or per_host < 1:
        raise ValueError("worker limits must be positive")
    waves: list[list[str]] = []
    wave: list[str] = []
    host_counts: dict[str, int] = {}
    for url in urls:
        host = (urlsplit(url).hostname or "").casefold()
        if wave and (
            len(wave) >= max_workers or host_counts.get(host, 0) >= per_host
        ):
            waves.append(wave)
            wave = []
            host_counts = {}
        wave.append(url)
        host_counts[host] = host_counts.get(host, 0) + 1
    if wave:
        waves.append(wave)
    return waves


def _default_fetch(url: str) -> FetchResult:
    from fetch_page import fetch_page

    return fetch_page(url)


def _fetch_worker(url: str) -> tuple[str, FetchResult]:
    return url, _default_fetch(url)


def _fetch_in_processes(urls: list[str]) -> dict[str, FetchResult]:
    results: dict[str, FetchResult] = {}
    waves = build_fetch_waves(urls)
    with ProcessPoolExecutor(max_workers=DEFAULT_GLOBAL_WORKERS) as executor:
        for wave in waves:
            for url, result in executor.map(_fetch_worker, wave):
                results[url] = result
    return results


def _filtered_headers(headers: object) -> dict[str, str]:
    if not isinstance(headers, dict):
        return {}
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in _SAFE_RESPONSE_HEADERS
    }


def _fallback_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "template", "noscript", "nav"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _language(html: str, text: str) -> str | None:
    soup = BeautifulSoup(html[:128_000], "html.parser")
    root = soup.find("html")
    declared = root.get("lang") if root else None
    if isinstance(declared, str) and declared.strip():
        return declared.strip().replace("_", "-").lower()
    hangul = sum("HANGUL" in unicodedata.name(char, "") for char in text[:16_000])
    latin = sum("LATIN" in unicodedata.name(char, "") for char in text[:16_000])
    if hangul > latin and hangul:
        return "ko"
    if latin:
        return "en"
    return None


def _extract_entities(structured: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    stack: list[object] = []
    for block in structured.get("blocks", []):
        if isinstance(block, dict) and "data" in block:
            stack.append(block["data"])
    visited = 0
    while stack and len(found) < MAX_ENTITIES and visited < 10_000:
        value = stack.pop()
        visited += 1
        if isinstance(value, dict):
            entity_type = value.get("@type")
            if isinstance(entity_type, list):
                entity_type = ", ".join(
                    item for item in entity_type if isinstance(item, str)
                )
            name = value.get("name") or value.get("headline")
            if isinstance(name, str) and name.strip():
                key = (str(entity_type or "Thing"), name.strip())
                if key not in seen:
                    seen.add(key)
                    entity: dict[str, Any] = {
                        "type": key[0],
                        "name": key[1],
                        "source": "structured-data",
                    }
                    identifier = value.get("@id") or value.get("url")
                    if isinstance(identifier, str):
                        entity["identifier"] = identifier
                    found.append(entity)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return found


def _structured_summary(structured: dict[str, Any]) -> dict[str, Any]:
    summary = copy.deepcopy(structured)
    for block in summary.get("blocks", []):
        if isinstance(block, dict):
            block.pop("data", None)
            block.pop("raw", None)
    return summary


def _public_record(record: dict[str, Any], *, include_html: bool) -> dict[str, Any]:
    bundle = copy.deepcopy(record["bundle"])
    if include_html:
        bundle["html"] = {
            "raw": record.get("raw_html"),
            "rendered": record.get("rendered_html"),
        }
    return bundle


class EvidenceEngine:
    """Per-audit collector that deduplicates fetches and renderer startup."""

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        renderer_factory: RendererFactory | None = None,
        render_mode: str = "auto",
        local_cache: bool = False,
        cache_dir: str | os.PathLike[str] | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        now: Callable[[], float] = time.time,
    ) -> None:
        if render_mode not in {"auto", "always", "never"}:
            raise ValueError("render_mode must be auto, always, or never")
        if cache_ttl_seconds < 1:
            raise ValueError("cache_ttl_seconds must be positive")
        self._fetcher = fetcher or _default_fetch
        self._uses_default_fetcher = fetcher is None
        self._renderer_factory = renderer_factory or RenderSession
        self._renderer: Any | None = None
        self._render_mode = render_mode
        self._run_cache: dict[str, dict[str, Any]] = {}
        self._local_cache = local_cache
        self._cache_dir = self._resolve_cache_dir(cache_dir) if local_cache else None
        self._cache_ttl = cache_ttl_seconds
        self._now = now

    def __enter__(self) -> "EvidenceEngine":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._renderer is None:
            return
        exit_method = getattr(self._renderer, "__exit__", None)
        if exit_method:
            exit_method(None, None, None)
        else:
            close = getattr(self._renderer, "close", None)
            if close:
                close()
        self._renderer = None

    @staticmethod
    def _resolve_cache_dir(raw: str | os.PathLike[str] | None) -> Path:
        if raw is None:
            base = os.environ.get("AUTOSEO_DATA_DIR")
            if base:
                path = Path(base).expanduser() / "cache" / "evidence-v1"
            else:
                path = Path.home() / ".cache" / "autoseo" / "evidence-v1"
        else:
            path = Path(raw).expanduser()
        path = path.resolve(strict=False)
        if path == Path(path.anchor).resolve() or path == Path.home().resolve():
            raise ValueError("cache must use a dedicated subdirectory")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.chmod(0o700)
        except OSError:
            pass
        return path

    def _cache_path(self, url: str) -> Path:
        assert self._cache_dir is not None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def _load_local(self, url: str) -> dict[str, Any] | None:
        if self._cache_dir is None:
            return None
        path = self._cache_path(url)
        if path.is_symlink():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            stored_at = float(value["stored_at"])
            bundle = value["bundle"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if self._now() - stored_at > self._cache_ttl or not isinstance(bundle, dict):
            return None
        cached = copy.deepcopy(bundle)
        cached.setdefault("cache", {})["source"] = "local-24h"
        return {"bundle": cached, "raw_html": None, "rendered_html": None}

    @staticmethod
    def _cache_eligible(url: str, raw: FetchResult) -> bool:
        parts = {part.casefold() for part in urlsplit(url).path.split("/") if part}
        headers = raw.get("headers") if isinstance(raw.get("headers"), dict) else {}
        lower_headers = {str(key).casefold(): str(value) for key, value in headers.items()}
        return (
            not (parts & _PRIVATE_PATH_PARTS)
            and raw.get("status_code") == 200
            and not raw.get("error")
            and "set-cookie" not in lower_headers
            and "www-authenticate" not in lower_headers
        )

    def _save_local(self, url: str, raw: FetchResult, record: dict[str, Any]) -> None:
        if self._cache_dir is None or not self._cache_eligible(url, raw):
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "stored_at": self._now(),
            "bundle": record["bundle"],
        }
        write_text_atomically(
            self._cache_path(url),
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            extensions={".json"},
        )

    def _ensure_renderer(self) -> Any:
        if self._renderer is None:
            renderer = self._renderer_factory()
            enter = getattr(renderer, "__enter__", None)
            self._renderer = enter() if enter else renderer
        return self._renderer

    def collect(self, url: str, *, include_html: bool = False) -> dict[str, Any]:
        canonical = _canonical_url(url)
        if canonical in self._run_cache:
            return _public_record(self._run_cache[canonical], include_html=include_html)
        if not include_html:
            cached = self._load_local(canonical)
            if cached is not None:
                self._run_cache[canonical] = cached
                return _public_record(cached, include_html=False)
        started = time.monotonic()
        raw = self._fetcher(canonical)
        fetch_ms = (time.monotonic() - started) * 1000.0
        record = self._build_record(canonical, raw, fetch_ms=fetch_ms)
        self._run_cache[canonical] = record
        self._save_local(canonical, raw, record)
        return _public_record(record, include_html=include_html)

    def collect_many(
        self,
        urls: Iterable[str],
        *,
        page_limit: int = DEFAULT_PAGE_LIMIT,
        include_html: bool = False,
    ) -> list[dict[str, Any]]:
        values = [_canonical_url(url) for url in urls]
        if not 1 <= page_limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"page limit must be between 1 and {MAX_PAGE_LIMIT}")
        if len(values) > page_limit:
            raise ValueError(f"URL count exceeds the {page_limit}-page limit")

        unique = list(dict.fromkeys(values))
        if self._uses_default_fetcher and len(unique) > 1:
            missing: list[str] = []
            for url in unique:
                if url in self._run_cache:
                    continue
                cached = None if include_html else self._load_local(url)
                if cached is not None:
                    self._run_cache[url] = cached
                else:
                    missing.append(url)
            started = time.monotonic()
            fetched = _fetch_in_processes(missing) if missing else {}
            elapsed_ms = (time.monotonic() - started) * 1000.0
            per_url_ms = elapsed_ms / max(1, len(missing))
            for url in missing:
                raw = fetched[url]
                record = self._build_record(url, raw, fetch_ms=per_url_ms)
                self._run_cache[url] = record
                self._save_local(url, raw, record)
        else:
            for url in unique:
                self.collect(url, include_html=include_html)
        return [
            _public_record(self._run_cache[url], include_html=include_html)
            for url in values
        ]

    def _build_record(
        self, url: str, raw: FetchResult, *, fetch_ms: float
    ) -> dict[str, Any]:
        raw_html = raw.get("content") if isinstance(raw.get("content"), str) else ""
        selected_html = raw_html
        is_spa = _is_spa(raw_html)
        should_render = self._render_mode == "always" or (
            self._render_mode == "auto" and is_spa
        )
        render_result: dict[str, Any] = {}
        if should_render:
            renderer = self._ensure_renderer()
            render_result = renderer.render(url)
            if not render_result.get("error") and isinstance(
                render_result.get("content"), str
            ):
                selected_html = render_result["content"]

        parsed = parse_html(selected_html, render_result.get("url") or raw.get("url") or url)
        full_text = _fallback_text(selected_html)
        text = full_text[:DEFAULT_BODY_CHARS]
        structured_full = _extract_json_ld(selected_html, include_full=True)
        links = parsed.pop("links", {"internal": [], "external": []})
        parsed.pop("schema", None)
        images = parsed.pop("images", [])
        observed_at = datetime.fromtimestamp(self._now(), tz=timezone.utc).isoformat()
        source_url = str(raw.get("url") or url)
        status_code = render_result.get("status_code") or raw.get("status_code")
        error = raw.get("error") or render_result.get("error")
        bundle = {
            "schema_version": SCHEMA_VERSION,
            "kind": "EvidenceBundle",
            "url": source_url,
            "requested_url": url,
            "collected_at": observed_at,
            "source_response": {
                "status_code": status_code,
                "headers": _filtered_headers(raw.get("headers")),
                "redirect_chain": raw.get("redirect_chain") or [],
                "body_chars": len(raw_html),
                "body_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
                "error": raw.get("error"),
            },
            "render": {
                "attempted": should_render,
                "is_spa": is_spa,
                "mode_used": "rendered"
                if should_render and not render_result.get("error")
                else "raw",
                "engine": render_result.get("render_engine"),
                "duration_ms": render_result.get("render_ms"),
                "diagnostics": render_result.get("render_diagnostics") or [],
                "error": render_result.get("error"),
            },
            "content": {
                "text": text,
                "text_chars": len(text),
                "original_text_chars": len(full_text),
                "truncated": len(full_text) > DEFAULT_BODY_CHARS,
                "language": _language(selected_html, full_text),
            },
            "metadata": {
                **parsed,
                "image_count": len(images),
                "publication_date": render_result.get("publication_date"),
            },
            "links": {
                "internal": links.get("internal", [])[:MAX_LINKS_PER_KIND],
                "external": links.get("external", [])[:MAX_LINKS_PER_KIND],
            },
            "structured_data": _structured_summary(structured_full),
            "entities": _extract_entities(structured_full),
            "performance_signals": {
                "fetch_ms": round(fetch_ms, 3),
                "render_ms": render_result.get("render_ms"),
                "response_chars": len(raw_html),
            },
            "cache": {"source": "run", "local_cache_enabled": self._local_cache},
            "error": error,
        }
        return {
            "bundle": bundle,
            "raw_html": raw_html,
            "rendered_html": selected_html if selected_html != raw_html else None,
        }


def _page_limit(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_PAGE_LIMIT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_PAGE_LIMIT}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="collect shared AutoSEO evidence")
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--page-limit", type=_page_limit, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--render", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--local-cache", action="store_true")
    parser.add_argument(
        "--include-html",
        action="store_true",
        help="include full HTML only for an explicitly requested artifact",
    )
    args = parser.parse_args(argv)
    try:
        with EvidenceEngine(
            render_mode=args.render, local_cache=args.local_cache
        ) as engine:
            bundles = engine.collect_many(
                args.urls,
                page_limit=args.page_limit,
                include_html=args.include_html,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(bundles, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
