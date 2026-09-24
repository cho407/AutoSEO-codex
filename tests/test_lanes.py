from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lane_engine import (  # noqa: E402
    ALL_LANES,
    analyze_lanes,
    build_lane_report,
    score_checks,
    select_lanes,
)


def _check(
    identifier: str,
    status: str,
    severity: str,
    *,
    required: bool = False,
) -> dict:
    return {
        "id": identifier,
        "status": status,
        "severity": severity,
        "applicable": True,
        "required": required,
        "evidence": [],
    }


def _bundle() -> dict:
    return {
        "schema_version": 1,
        "kind": "EvidenceBundle",
        "url": "https://example.com/guide",
        "requested_url": "https://example.com/guide",
        "collected_at": "2026-08-28T00:00:00+00:00",
        "source_response": {"status_code": 200, "error": None},
        "render": {"attempted": False, "is_spa": False, "error": None},
        "content": {
            "text": "무엇인지 바로 설명하는 한국어 안내입니다. 근거와 예시를 제공합니다.",
            "text_chars": 38,
            "language": "ko",
        },
        "metadata": {
            "title": "한국어 안내",
            "meta_robots": "index,follow",
            "canonical": "https://example.com/guide",
            "h1": ["무엇인가요?"],
            "h2": ["근거"],
        },
        "links": {
            "internal": [],
            "external": [{"href": "https://example.org/source"}],
        },
        "structured_data": {"block_count": 1},
        "entities": [{"type": "Person", "name": "홍길동"}],
        "performance_signals": {},
    }


def test_unmeasured_checks_are_not_converted_to_zero() -> None:
    result = score_checks(
        [
            _check("eligibility", "pass", "critical", required=True),
            _check("quality", "fail", "high"),
            _check("unknown", "unmeasured", "medium"),
        ]
    )

    assert result["coverage_percent"] == 77.8
    assert result["score"] == 57.1
    assert result["unmeasured_weight"] == 2


def test_required_unmeasured_check_suppresses_score() -> None:
    result = score_checks(
        [
            _check("eligibility", "unmeasured", "critical", required=True),
            _check("quality", "pass", "high"),
        ]
    )

    assert result["score"] is None
    assert result["score_displayed"] is False
    assert "required" in result["reason"]


def test_outcome_panel_does_not_change_readiness_score() -> None:
    checks = [
        _check("eligibility", "pass", "critical", required=True),
        _check("quality", "fail", "high"),
    ]
    baseline = build_lane_report(
        "geo", "example.com", checks, outcomes=[], market="US", language="en"
    )
    observed = build_lane_report(
        "geo",
        "example.com",
        checks,
        outcomes=[{"metric": "citation_share", "numerator": 9, "denominator": 10}],
        market="US",
        language="en",
    )

    assert baseline["readiness"] == observed["readiness"]
    assert baseline["outcomes"] == []
    assert len(observed["outcomes"]) == 1
    dimensions = observed["observations"][0]
    for key in (
        "numerator",
        "denominator",
        "market",
        "language",
        "surface",
        "measured_at",
        "confidence",
        "limitations",
    ):
        assert key in dimensions


def test_automatic_lane_selection_is_deterministic() -> None:
    assert select_lanes("https://example.com/") == ("seo",)
    assert select_lanes(
        "네이버 블로그 글을 어떻게 작성하나요?", market="KR", language="ko"
    ) == ("aeo", "neo")
    assert select_lanes("Acme brand ChatGPT citations") == ("geo", "llmo")
    assert select_lanes(
        "https://example.com/", request="AI citations for this brand"
    ) == ("seo", "geo", "llmo")
    assert select_lanes("anything", run_all=True) == ALL_LANES


def test_each_lane_returns_an_independent_versioned_report() -> None:
    reports = analyze_lanes(
        _bundle(),
        target="무엇인가요?",
        lanes=ALL_LANES,
        market="KR",
        language="ko",
    )

    assert tuple(reports) == ALL_LANES
    assert all(report["schema_version"] == 1 for report in reports.values())
    assert all(report["kind"] == "LaneReport" for report in reports.values())
    assert reports["llmo"]["readiness"]["score"] is None
    neo_intent = next(
        item for item in reports["neo"]["checks"] if item["id"] == "korean_intent"
    )
    assert neo_intent["status"] == "pass"
    closed_book = next(
        item
        for item in reports["llmo"]["checks"]
        if item["id"] == "closed_book_model_knowledge"
    )
    assert closed_book["status"] == "unmeasured"


def test_neo_public_readiness_contract_accepts_normal_public_evidence() -> None:
    report = analyze_lanes(
        _bundle(),
        target="무엇인가요?",
        lanes=("neo",),
        market="KR",
        language="ko",
    )["neo"]

    assert [check["id"] for check in report["checks"]] == [
        "public_naver_access",
        "korean_language",
        "korean_intent",
        "yeti_policy",
        "rss_or_sitemap",
    ]
