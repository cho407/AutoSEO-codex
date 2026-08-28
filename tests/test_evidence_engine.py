from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_page  # noqa: E402
from evidence_engine import (  # noqa: E402
    EvidenceEngine,
    build_fetch_waves,
)

STATIC_HTML = """<!doctype html>
<html lang="ko"><head><title>테스트 페이지</title>
<meta name="description" content="설명">
<script type="application/ld+json">
{{"@type":"Article","headline":"근거 기반 글","author":{{"@type":"Person","name":"홍길동"}}}}
</script></head><body><main><h1>안녕하세요</h1><p>{body}</p>
<a href="/about">소개</a></main></body></html>"""


def _raw(url: str, html: str) -> dict:
    return {
        "url": url,
        "status_code": 200,
        "content": html,
        "headers": {"Content-Type": "text/html; charset=utf-8", "Set-Cookie": "secret=1"},
        "redirect_chain": [],
        "error": None,
    }


class FakeRenderer:
    def __init__(self) -> None:
        self.enter_count = 0
        self.render_count = 0
        self.exit_count = 0

    def __enter__(self) -> "FakeRenderer":
        self.enter_count += 1
        return self

    def __exit__(self, *_: object) -> None:
        self.exit_count += 1

    def render(self, url: str, **_: object) -> dict:
        self.render_count += 1
        return {
            "url": url,
            "status_code": 200,
            "content": STATIC_HTML.format(body="렌더링 완료 " * 80),
            "headers": {"content-type": "text/html"},
            "console_errors": [],
            "render_diagnostics": [],
            "render_engine": "fake-chromium",
            "render_ms": 5.0,
            "accessibility_tree": None,
            "accessibility_error": None,
            "accessibility_partial": False,
            "error": None,
        }


def test_same_url_is_fetched_once_and_body_is_bounded() -> None:
    calls: Counter[str] = Counter()

    def fetcher(url: str) -> dict:
        calls[url] += 1
        return _raw(url, STATIC_HTML.format(body="가" * 20_000))

    with EvidenceEngine(fetcher=fetcher) as engine:
        first = engine.collect("https://example.com/article")
        second = engine.collect("https://example.com/article")

    assert calls == {"https://example.com/article": 1}
    assert first == second
    assert first["schema_version"] == 1
    assert first["content"]["language"] == "ko"
    assert first["content"]["text_chars"] == 16_000
    assert first["content"]["truncated"] is True
    assert first["metadata"]["title"] == "테스트 페이지"
    assert first["structured_data"]["block_count"] == 1
    assert {item["name"] for item in first["entities"]} >= {"홍길동"}
    assert "Set-Cookie" not in first["source_response"]["headers"]
    assert first["render"]["attempted"] is False
    assert "html" not in first


def test_spa_pages_share_one_renderer_and_never_refetch() -> None:
    calls: Counter[str] = Counter()
    renderer = FakeRenderer()

    def fetcher(url: str) -> dict:
        calls[url] += 1
        return _raw(url, '<html><body><div id="root"></div></body></html>')

    with EvidenceEngine(fetcher=fetcher, renderer_factory=lambda: renderer) as engine:
        bundles = engine.collect_many(
            ["https://example.com/a", "https://example.com/b"]
        )

    assert len(bundles) == 2
    assert calls == {"https://example.com/a": 1, "https://example.com/b": 1}
    assert renderer.enter_count == 1
    assert renderer.render_count == 2
    assert renderer.exit_count == 1
    assert all(item["render"]["attempted"] for item in bundles)


def test_collect_many_enforces_page_limits() -> None:
    with EvidenceEngine(fetcher=lambda url: _raw(url, STATIC_HTML.format(body="본문"))) as engine:
        with pytest.raises(ValueError, match="page limit"):
            engine.collect_many([f"https://example.com/{index}" for index in range(101)])
        with pytest.raises(ValueError, match="500"):
            engine.collect_many(["https://example.com/"], page_limit=501)


def test_process_fetch_waves_bound_global_and_per_host_concurrency() -> None:
    urls = [
        *(f"https://a.example/{index}" for index in range(5)),
        *(f"https://b.example/{index}" for index in range(4)),
        *(f"https://c.example/{index}" for index in range(3)),
    ]
    waves = build_fetch_waves(urls, max_workers=4, per_host=2)

    assert [url for wave in waves for url in wave] == urls
    for wave in waves:
        assert len(wave) <= 4
        hosts = Counter(url.split("/", 3)[2] for url in wave)
        assert max(hosts.values()) <= 2


def test_public_local_cache_is_opt_in_and_never_stores_cookie_pages(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    public = _raw("https://example.com/public", STATIC_HTML.format(body="공개 본문"))
    public["headers"].pop("Set-Cookie")

    with EvidenceEngine(
        fetcher=lambda _: public,
        local_cache=True,
        cache_dir=cache_dir,
        now=lambda: 1_000.0,
        render_mode="never",
    ) as engine:
        engine.collect("https://example.com/public")

    assert len(list(cache_dir.glob("*.json"))) == 1

    with EvidenceEngine(
        fetcher=lambda _: pytest.fail("fresh public cache must be reused"),
        local_cache=True,
        cache_dir=cache_dir,
        now=lambda: 1_001.0,
        render_mode="never",
    ) as engine:
        cached = engine.collect("https://example.com/public")
    assert cached["cache"]["source"] == "local-24h"

    cookie_cache = tmp_path / "cookie-cache"
    with EvidenceEngine(
        fetcher=lambda url: _raw(url, STATIC_HTML.format(body="개인화")),
        local_cache=True,
        cache_dir=cookie_cache,
        now=lambda: 1_000.0,
        render_mode="never",
    ) as engine:
        engine.collect("https://example.com/account")
    assert list(cookie_cache.glob("*.json")) == []


def test_evidence_schema_declares_bounded_text_contract() -> None:
    import json

    schema = json.loads(
        (
            ROOT
            / "plugins"
            / "autoseo"
            / "schema"
            / "evidence-bundle.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["content"]["properties"]["text"]["maxLength"] == 16_000


def test_render_session_launches_chromium_once_per_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        @staticmethod
        def all_headers() -> dict[str, str]:
            return {"content-type": "text/html"}

    class Page:
        def __init__(self, url: str = "") -> None:
            self.url = url

        def on(self, *_: object) -> None:
            pass

        def route(self, *_: object) -> None:
            pass

        def goto(self, url: str, **_: object) -> Response:
            self.url = url
            return Response()

        def evaluate(self, *_: object) -> list[int]:
            return [200, 20]

        def wait_for_timeout(self, *_: object) -> None:
            pass

        def content(self) -> str:
            return STATIC_HTML.format(body="브라우저 본문 " * 20)

        def close(self) -> None:
            pass

    class Context:
        def __init__(self) -> None:
            self.pages = 0

        def new_page(self) -> Page:
            self.pages += 1
            return Page()

        def close(self) -> None:
            pass

    class Browser:
        def __init__(self) -> None:
            self.launches = 0
            self.context = Context()

        def new_context(self, **_: object) -> Context:
            return self.context

        def close(self) -> None:
            pass

    browser = Browser()

    class Chromium:
        def launch(self, **_: object) -> Browser:
            browser.launches += 1
            return browser

    class Playwright:
        chromium = Chromium()

        def stop(self) -> None:
            pass

    class Factory:
        @staticmethod
        def start() -> Playwright:
            return Playwright()

    monkeypatch.setattr(render_page, "sync_playwright", lambda: Factory())
    monkeypatch.setattr(
        render_page, "validate_url_strict", lambda url: (url, "93.184.216.34")
    )
    monkeypatch.setattr(
        render_page, "make_safe_playwright_route_handler", lambda _: object()
    )

    with render_page.RenderSession() as session:
        first = session.render("https://example.com/a")
        second = session.render("https://example.com/b")

    assert first["error"] is None
    assert second["error"] is None
    assert browser.launches == 1
    assert session.launch_count == 1
    assert browser.context.pages == 2
