from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from benchmark_evidence import run_benchmark  # noqa: E402


def test_shared_evidence_meets_bounded_20_page_performance_targets() -> None:
    result = run_benchmark(repeats=3, latency_ms=5.0)

    assert result["fixture"]["pages"] == 20
    assert result["multi_page"]["legacy_fetches"] == 100
    assert result["multi_page"]["shared_fetches"] == 20
    assert result["multi_page"]["reduction_pct"] >= 30.0
    assert result["single_page"]["regression_pct"] <= 10.0
    assert result["passed"] is True


def test_benchmark_rejects_non_finite_or_unstable_inputs() -> None:
    for value in (math.nan, math.inf, -math.inf, -1.0, 1_001.0):
        try:
            run_benchmark(repeats=3, latency_ms=value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe latency accepted: {value}")
