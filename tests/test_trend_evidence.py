from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from trend_evidence import analyze_trends, validate_trend_evidence  # noqa: E402


def _evidence() -> dict:
    return {
        "schema_version": 1,
        "kind": "TrendEvidence",
        "topic": "AI 검색 최적화",
        "market": "KR",
        "language": "ko",
        "window": "24h",
        "observed_at": "2026-08-31T12:00:00+00:00",
        "evidence": [
            {
                "source_type": "official-trend",
                "source_group": "google-trends",
                "url": "https://trends.google.com/trending?geo=KR&utm_source=test",
                "title": "AI 검색 최적화 관심 증가",
                "published_at": "2026-08-31T11:30:00+00:00",
                "metrics": {"velocity_index": 90},
            },
            {
                "source_type": "primary-source",
                "source_group": "example-product",
                "url": "https://example.com/news/ai-search",
                "title": "AI 검색 최적화 기능 공개",
                "published_at": "2026-08-31T10:00:00+00:00",
                "event_at": "2026-08-31T09:30:00+00:00",
                "is_primary": True,
            },
            {
                "source_type": "news",
                "source_group": "news-example",
                "url": "https://news.example.org/ai-search",
                "title": "AI 검색 최적화가 주목받는 이유",
                "published_at": "2026-08-31T09:00:00+00:00",
            },
            {
                "source_type": "primary-source",
                "source_group": "example-product",
                "url": "https://example.com/news/ai-search?utm_campaign=duplicate",
                "title": "AI 검색 최적화 기능 공개",
                "published_at": "2026-08-31T10:00:00+00:00",
                "is_primary": True,
            },
        ],
    }


def test_trend_evidence_deduplicates_and_requires_independent_corroboration() -> None:
    result = analyze_trends(
        _evidence(), as_of="2026-08-31T12:30:00+00:00"
    )

    assert result["schema_version"] == 1
    assert result["kind"] == "TrendReport"
    assert result["evidence_count"] == 3
    assert result["duplicate_count"] == 1
    assert result["independent_source_count"] == 3
    assert result["corroboration_status"] == "confirmed"
    assert result["opportunity"]["score"] is not None
    assert result["opportunity"]["exact_search_volume"] is None
    assert result["content_action"] == "brief-ready"


def test_shipped_trend_evidence_example_matches_runtime_contract() -> None:
    example = json.loads(
        (ROOT / "plugins" / "autoseo" / "examples" / "trend-evidence-v1.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (ROOT / "plugins" / "autoseo" / "schema" / "trend-evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert validate_trend_evidence(example)["kind"] == "TrendEvidence"
    assert schema["properties"]["schema_version"]["const"] == 1


def test_trend_refresh_policy_is_window_specific_and_machine_readable() -> None:
    fresh = analyze_trends(_evidence(), as_of="2026-08-31T13:00:00+00:00")
    old = analyze_trends(_evidence(), as_of="2026-08-31T15:00:01+00:00")

    assert fresh["refresh"]["refresh_after"] == "2026-08-31T14:00:00+00:00"
    assert fresh["refresh"]["needs_refresh"] is False
    assert old["refresh"]["needs_refresh"] is True


def test_single_source_trend_is_not_presented_as_confirmed() -> None:
    value = _evidence()
    value["evidence"] = value["evidence"][:1]

    result = analyze_trends(value, as_of=value["observed_at"])

    assert result["corroboration_status"] == "measured-single-source"
    assert result["content_action"] == "corroborate-before-brief"
    assert result["limitations"]


def test_trend_timestamps_must_be_timezone_aware_and_not_future_dated() -> None:
    value = _evidence()
    value["observed_at"] = "2026-08-31T12:00:00"
    with pytest.raises(ValueError, match="timezone"):
        validate_trend_evidence(value)

    value = _evidence()
    value["evidence"][0]["published_at"] = "2026-08-31T12:10:01+00:00"
    with pytest.raises(ValueError, match="future"):
        validate_trend_evidence(value)


def test_trend_metrics_reject_nan_and_out_of_range_values() -> None:
    value = _evidence()
    value["evidence"][0]["metrics"]["velocity_index"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        validate_trend_evidence(value)

    value = _evidence()
    value["evidence"][0]["metrics"]["velocity_index"] = 101
    with pytest.raises(ValueError, match="between 0 and 100"):
        validate_trend_evidence(value)


def test_one_hostname_cannot_claim_multiple_independent_source_groups() -> None:
    value = _evidence()
    value["evidence"][1]["source_group"] = "publisher-one"
    duplicate_host = dict(value["evidence"][1])
    duplicate_host["url"] = "https://example.com/news/another-ai-search"
    duplicate_host["title"] = "AI 검색 최적화 후속 기능"
    duplicate_host["source_group"] = "publisher-two"
    value["evidence"].append(duplicate_host)

    with pytest.raises(ValueError, match="one source_group"):
        validate_trend_evidence(value)
