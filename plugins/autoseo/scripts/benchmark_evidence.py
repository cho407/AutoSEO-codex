#!/usr/bin/env python3
"""Reproducible Evidence Engine benchmark over a local 20-page fixture site."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from typing import Any

from evidence_engine import EvidenceEngine

LANES = ("seo", "aeo", "geo", "llmo", "neo")
PAGE_COUNT = 20
TARGET_MULTI_PAGE_REDUCTION_PCT = 30.0
MAX_SINGLE_PAGE_REGRESSION_PCT = 10.0


def _html(index: int) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><title>로컬 성능 픽스처 {index}</title>
<meta name="description" content="Evidence Engine 비교 페이지">
</head><body><main><h1>페이지 {index}</h1>
<p>다섯 최적화 레인이 함께 재사용하는 근거 본문입니다. {index}</p>
<a href="/page-{(index + 1) % PAGE_COUNT}">다음 페이지</a>
</main></body></html>"""


@dataclass
class LocalFixtureSite:
    """Serve deterministic local fixture bytes without DNS or network variance."""

    latency_seconds: float
    calls: int = 0

    @property
    def urls(self) -> list[str]:
        return [f"https://benchmark.example/page-{index}" for index in range(PAGE_COUNT)]

    def fetch(self, url: str) -> dict[str, Any]:
        self.calls += 1
        if self.latency_seconds:
            time.sleep(self.latency_seconds)
        index = int(url.rsplit("-", 1)[-1])
        content = _html(index)
        return {
            "url": url,
            "status_code": 200,
            "content": content,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "redirect_chain": [],
            "error": None,
        }


def _elapsed(callback: Any) -> float:
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def _legacy_multi_page(latency_seconds: float) -> tuple[float, int]:
    site = LocalFixtureSite(latency_seconds)

    def run() -> None:
        for _lane in LANES:
            with EvidenceEngine(fetcher=site.fetch, render_mode="never") as engine:
                engine.collect_many(site.urls, page_limit=PAGE_COUNT)

    return _elapsed(run), site.calls


def _shared_multi_page(latency_seconds: float) -> tuple[float, int]:
    site = LocalFixtureSite(latency_seconds)

    def run() -> None:
        with EvidenceEngine(fetcher=site.fetch, render_mode="never") as engine:
            for _lane in LANES:
                engine.collect_many(site.urls, page_limit=PAGE_COUNT)

    return _elapsed(run), site.calls


def _single_page(latency_seconds: float) -> tuple[float, float]:
    baseline_site = LocalFixtureSite(latency_seconds)
    shared_site = LocalFixtureSite(latency_seconds)
    url = baseline_site.urls[0]

    def baseline() -> None:
        with EvidenceEngine(fetcher=baseline_site.fetch, render_mode="never") as engine:
            engine.collect(url)

    def shared() -> None:
        with EvidenceEngine(fetcher=shared_site.fetch, render_mode="never") as engine:
            engine.collect(url)

    return _elapsed(baseline), _elapsed(shared)


def run_benchmark(*, repeats: int = 5, latency_ms: float = 5.0) -> dict[str, Any]:
    if repeats < 3:
        raise ValueError("repeats must be at least 3 for a median benchmark")
    if not 0 <= latency_ms <= 1_000:
        raise ValueError("latency_ms must be between 0 and 1000")
    latency_seconds = latency_ms / 1_000.0
    legacy_values: list[float] = []
    shared_values: list[float] = []
    baseline_single_values: list[float] = []
    shared_single_values: list[float] = []
    legacy_fetches = 0
    shared_fetches = 0

    for _ in range(repeats):
        legacy_elapsed, legacy_fetches = _legacy_multi_page(latency_seconds)
        shared_elapsed, shared_fetches = _shared_multi_page(latency_seconds)
        baseline_single, shared_single = _single_page(latency_seconds)
        legacy_values.append(legacy_elapsed)
        shared_values.append(shared_elapsed)
        baseline_single_values.append(baseline_single)
        shared_single_values.append(shared_single)

    legacy_median = statistics.median(legacy_values)
    shared_median = statistics.median(shared_values)
    baseline_single_median = statistics.median(baseline_single_values)
    shared_single_median = statistics.median(shared_single_values)
    reduction = 100.0 * (legacy_median - shared_median) / legacy_median
    regression = (
        100.0
        * (shared_single_median - baseline_single_median)
        / baseline_single_median
    )
    return {
        "schema_version": 1,
        "fixture": {
            "kind": "local-in-memory-site",
            "pages": PAGE_COUNT,
            "lanes": list(LANES),
            "simulated_fetch_latency_ms": latency_ms,
            "repeats": repeats,
        },
        "multi_page": {
            "legacy_median_ms": round(legacy_median * 1_000.0, 3),
            "shared_median_ms": round(shared_median * 1_000.0, 3),
            "reduction_pct": round(reduction, 3),
            "target_reduction_pct": TARGET_MULTI_PAGE_REDUCTION_PCT,
            "legacy_fetches": legacy_fetches,
            "shared_fetches": shared_fetches,
            "passed": reduction >= TARGET_MULTI_PAGE_REDUCTION_PCT,
        },
        "single_page": {
            "baseline_median_ms": round(baseline_single_median * 1_000.0, 3),
            "shared_median_ms": round(shared_single_median * 1_000.0, 3),
            "regression_pct": round(regression, 3),
            "maximum_regression_pct": MAX_SINGLE_PAGE_REGRESSION_PCT,
            "passed": regression <= MAX_SINGLE_PAGE_REGRESSION_PCT,
        },
        "passed": reduction >= TARGET_MULTI_PAGE_REDUCTION_PCT
        and regression <= MAX_SINGLE_PAGE_REGRESSION_PCT,
        "note": (
            "The fixture isolates collection architecture; it is not a prediction "
            "of internet or browser performance."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--latency-ms", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(repeats=args.repeats, latency_ms=args.latency_ms)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
