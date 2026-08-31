#!/usr/bin/env python3
"""Combine independent LaneReport v1 files into one transparent readiness score."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from file_safety import read_text_limited
from lane_engine import ALL_LANES, MINIMUM_COVERAGE_PERCENT, SEVERITY_WEIGHTS, score_checks

SCHEMA_VERSION = 1
_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _grade(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 90:
        return "excellent-readiness"
    if score >= 75:
        return "strong-readiness"
    if score >= 60:
        return "needs-improvement"
    return "weak-readiness"


def _validate_report(lane_key: str, value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{lane_key} report must be an object")
    report = copy.deepcopy(value)
    if report.get("schema_version") != 1 or report.get("kind") != "LaneReport":
        raise ValueError(f"{lane_key} must be a LaneReport v1")
    if report.get("lane") != lane_key:
        raise ValueError(f"lane key {lane_key!r} does not match report lane")
    if lane_key not in ALL_LANES:
        raise ValueError(f"unsupported lane: {lane_key}")
    if not isinstance(report.get("target"), str) or not report["target"].strip():
        raise ValueError(f"{lane_key} report target is missing")
    measured_at = report.get("measured_at")
    if not isinstance(measured_at, str):
        raise ValueError(f"{lane_key} report measured_at is missing")
    try:
        parsed = datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{lane_key} report measured_at must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{lane_key} report measured_at must include a timezone")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{lane_key} report requires checks")
    report["readiness"] = score_checks(checks)
    outcomes = report.get("outcomes", [])
    if not isinstance(outcomes, list):
        raise ValueError(f"{lane_key} outcomes must be a list")
    return report


def build_optimization_report(reports: Mapping[str, object]) -> dict[str, Any]:
    """Aggregate measured evidence while keeping observed outcomes separate."""
    if not isinstance(reports, Mapping) or not reports:
        raise ValueError("at least one lane report is required")
    if len(reports) > len(ALL_LANES):
        raise ValueError("at most five unique lane reports are supported")
    if any(not isinstance(lane, str) for lane in reports):
        raise ValueError("lane report keys must be strings")
    unknown = set(reports) - set(ALL_LANES)
    if unknown:
        raise ValueError(f"unsupported lanes: {sorted(unknown)}")
    normalized = [
        _validate_report(lane, reports[lane])
        for lane in ALL_LANES
        if lane in reports
    ]
    targets = {report["target"] for report in normalized}
    if len(targets) != 1:
        raise ValueError("all lane reports must describe the same target")

    applicable_weight = sum(
        report["readiness"]["applicable_weight"] for report in normalized
    )
    unmeasured_weight = sum(
        report["readiness"]["unmeasured_weight"] for report in normalized
    )
    pass_weight = sum(report["readiness"]["pass_weight"] for report in normalized)
    fail_weight = sum(report["readiness"]["fail_weight"] for report in normalized)
    measured_weight = applicable_weight - unmeasured_weight
    coverage = (
        round(measured_weight / applicable_weight * 100, 1)
        if applicable_weight
        else 0.0
    )
    withheld = [
        report["lane"]
        for report in normalized
        if report["readiness"]["score"] is None
    ]
    score: float | None = None
    reason: str | None = None
    if withheld:
        reason = "score withheld because these selected lanes are not scoreable: " + ", ".join(
            withheld
        )
    elif coverage < MINIMUM_COVERAGE_PERCENT:
        reason = (
            f"aggregate evidence coverage {coverage:.1f}% is below the "
            f"{MINIMUM_COVERAGE_PERCENT:.0f}% display threshold"
        )
    elif measured_weight:
        score = round(pass_weight / measured_weight * 100, 1)
    else:
        reason = "no applicable evidence was measured"

    lanes: list[dict[str, Any]] = []
    priorities: list[dict[str, Any]] = []
    outcomes: dict[str, list[dict[str, Any]]] = {}
    for report in normalized:
        readiness = report["readiness"]
        lanes.append(
            {
                "lane": report["lane"],
                "score": readiness["score"],
                "coverage_percent": readiness["coverage_percent"],
                "status": "scored" if readiness["score"] is not None else "withheld",
                "reason": readiness["reason"],
            }
        )
        outcomes[report["lane"]] = copy.deepcopy(report.get("outcomes", []))
        for check in report["checks"]:
            if check.get("status") != "fail" or not check.get("applicable", True):
                continue
            evidence = check.get("evidence", [])
            priorities.append(
                {
                    "lane": report["lane"],
                    "check_id": check["id"],
                    "severity": check["severity"],
                    "weight": SEVERITY_WEIGHTS[check["severity"]],
                    "evidence": copy.deepcopy(evidence[:3] if isinstance(evidence, list) else []),
                    "note": check.get("note"),
                }
            )
    lane_order = {lane: index for index, lane in enumerate(ALL_LANES)}
    priorities.sort(
        key=lambda item: (
            _PRIORITY_ORDER[item["severity"]],
            lane_order[item["lane"]],
            item["check_id"],
        )
    )
    measured_times = [
        datetime.fromisoformat(report["measured_at"].replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        for report in normalized
    ]
    confidence = (
        "high"
        if score is not None and coverage >= 90
        else "medium"
        if score is not None
        else "low"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "OptimizationReport",
        "target": normalized[0]["target"],
        "measured_at": max(measured_times).isoformat() if measured_times else None,
        "selected_lanes": [report["lane"] for report in normalized],
        "readiness": {
            "score": score,
            "score_displayed": score is not None,
            "grade": _grade(score),
            "coverage_percent": coverage,
            "coverage_threshold_percent": MINIMUM_COVERAGE_PERCENT,
            "pass_weight": pass_weight,
            "fail_weight": fail_weight,
            "unmeasured_weight": unmeasured_weight,
            "applicable_weight": applicable_weight,
            "confidence": confidence,
            "reason": reason,
            "method": "severity-weighted measured evidence across selected lanes",
            "meaning": "readiness only; not a ranking, traffic, exposure, or citation prediction",
        },
        "lanes": lanes,
        "priorities": priorities,
        "outcomes": outcomes,
        "limitations": [
            "A combined score appears only when every selected lane is independently scoreable.",
            "Unmeasured evidence is excluded from points and remains visible in coverage.",
            "Observed clicks, ranks, mentions, and citations never change readiness points.",
        ],
    }


def _load_reports(path: Path) -> Mapping[str, object]:
    value = json.loads(read_text_limited(path, extensions={".json"}))
    if not isinstance(value, dict):
        raise ValueError("input must be an object of lane reports")
    reports = value.get("reports", value)
    if not isinstance(reports, dict):
        raise ValueError("reports must be an object keyed by lane")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON object keyed by lane")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_optimization_report(_load_reports(args.input))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
