from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lane_engine import build_lane_report  # noqa: E402
from optimization_report import build_optimization_report  # noqa: E402


def _check(identifier: str, status: str, severity: str, required: bool = False) -> dict:
    return {
        "id": identifier,
        "status": status,
        "severity": severity,
        "applicable": True,
        "required": required,
        "evidence": [identifier],
    }


def _report(lane: str, checks: list[dict], outcomes: list[dict] | None = None) -> dict:
    return build_lane_report(
        lane,
        "https://example.com",
        checks,
        outcomes=outcomes or [],
        market="KR",
        language="ko",
        measured_at="2026-08-31T00:00:00+00:00",
    )


def test_optimization_report_aggregates_only_measured_readiness() -> None:
    reports = {
        "seo": _report(
            "seo",
            [
                _check("reachable", "pass", "critical", True),
                _check("title", "fail", "high"),
                _check("optional", "unmeasured", "low"),
            ],
        ),
        "neo": _report(
            "neo",
            [
                _check("public", "pass", "critical", True),
                _check("intent", "pass", "medium"),
            ],
        ),
    }

    result = build_optimization_report(reports)

    assert result["schema_version"] == 1
    assert result["kind"] == "OptimizationReport"
    assert result["readiness"]["score"] == 76.9
    assert result["readiness"]["coverage_percent"] == 92.9
    assert result["readiness"]["meaning"].startswith("readiness")
    assert result["selected_lanes"] == ["seo", "neo"]
    assert result["priorities"][0]["check_id"] == "title"


def test_any_withheld_required_lane_withholds_the_combined_score() -> None:
    reports = {
        "seo": _report(
            "seo", [_check("reachable", "pass", "critical", True)]
        ),
        "llmo": _report(
            "llmo", [_check("closed-book", "unmeasured", "critical", True)]
        ),
    }

    result = build_optimization_report(reports)

    assert result["readiness"]["score"] is None
    assert result["readiness"]["score_displayed"] is False
    assert "llmo" in result["readiness"]["reason"]
    assert result["lanes"][1]["status"] == "withheld"


def test_observed_results_never_change_the_optimization_readiness_score() -> None:
    checks = [
        _check("public", "pass", "critical", True),
        _check("source", "fail", "high"),
    ]
    baseline = build_optimization_report({"geo": _report("geo", checks)})
    observed = build_optimization_report(
        {
            "geo": _report(
                "geo",
                checks,
                outcomes=[
                    {"metric": "citation_share", "numerator": 10, "denominator": 10}
                ],
            )
        }
    )

    assert baseline["readiness"] == observed["readiness"]
    assert baseline["outcomes"]["geo"] == []
    assert len(observed["outcomes"]["geo"]) == 1


def test_duplicate_or_mismatched_lane_reports_are_rejected() -> None:
    report = _report("seo", [_check("public", "pass", "critical", True)])
    report["lane"] = "neo"

    try:
        build_optimization_report({"seo": report})
    except ValueError as exc:
        assert "lane key" in str(exc)
    else:
        raise AssertionError("mismatched lane report was accepted")


def test_lane_output_order_is_canonical_even_when_input_order_is_not() -> None:
    reports = {
        "neo": _report("neo", [_check("public", "pass", "critical", True)]),
        "seo": _report("seo", [_check("reachable", "pass", "critical", True)]),
    }

    result = build_optimization_report(reports)

    assert result["selected_lanes"] == ["seo", "neo"]


def test_optimization_report_schema_is_shipped_and_versioned() -> None:
    schema = json.loads(
        (ROOT / "plugins" / "autoseo" / "schema" / "optimization-report.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["kind"]["const"] == "OptimizationReport"
