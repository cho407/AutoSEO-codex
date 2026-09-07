"""Regressions for false confidence, stale evidence, and incomparable reports."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/autoseo/scripts"))

import lane_engine  # noqa: E402
from content_quality import analyse  # noqa: E402
from optimization_report import build_optimization_report  # noqa: E402
from test_lanes import _bundle  # noqa: E402
from test_trend_evidence import _evidence  # noqa: E402
from trend_evidence import analyze_trends  # noqa: E402


def _checks(bundle: dict, lane: str) -> dict:
    report = lane_engine.analyze_lanes(bundle, target=bundle["url"], lanes=[lane])[lane]
    return {check["id"]: check for check in report["checks"]}


def test_http_noindex_is_a_blocker_not_a_perfect_score() -> None:
    bundle = _bundle()
    bundle["source_response"]["headers"] = {"X-Robots-Tag": "noindex, nosnippet"}
    report = lane_engine.analyze_lanes(bundle, target=bundle["url"], lanes=["seo"])["seo"]
    assert _checks(bundle, "seo")["index_eligible"]["status"] == "fail"
    assert report["eligibility"]["status"] == "blocked"
    assert "index_eligible" in report["eligibility"]["blockers"]
    assert _checks(bundle, "aeo")["snippet_eligible"]["status"] == "fail"


def test_other_crawler_noindex_does_not_block_google() -> None:
    bundle = _bundle()
    bundle["source_response"]["headers"] = {"x-robots-tag": "otherbot: noindex"}
    assert _checks(bundle, "seo")["index_eligible"]["status"] == "pass"


def test_links_length_and_person_markup_do_not_prove_semantic_quality() -> None:
    bundle = _bundle()
    bundle["content"]["text"] *= 50
    bundle["content"]["text_chars"] = len(bundle["content"]["text"])
    for lane, identifiers in {
        "aeo": ["direct_answer", "claim_source_support", "authorship"],
        "geo": ["source_support", "entity_clarity", "search_crawler_policy"],
        "llmo": ["brand_fact_ledger", "external_corroboration"],
    }.items():
        checks = _checks(bundle, lane)
        assert all(checks[key]["status"] == "unmeasured" for key in identifiers)
    bundle["metadata"]["canonical"] = "https://unrelated.example/elsewhere"
    assert _checks(bundle, "seo")["canonical"]["status"] == "unmeasured"


def test_numeric_url_does_not_make_korean_intent_fail() -> None:
    bundle = _bundle()
    bundle["url"] = "https://example.com/12345"
    assert _checks(bundle, "neo")["korean_intent"]["status"] != "fail"
    assert "naver_search_or_ai_briefing" not in _checks(bundle, "neo")


def test_auto_audit_uses_detected_korean(tmp_path: Path, capsys) -> None:
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(_bundle()), encoding="utf-8")
    assert lane_engine.main(["audit", _bundle()["url"], "--bundle", str(path)]) == 0
    assert "neo" in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("field,value", [("market", "US"), ("language", "en"),
    ("question", "a different question"), ("rule_version", "other"),
    ("collected_at", "2026-08-29T00:00:00+00:00")])
def test_incompatible_audit_contexts_cannot_be_aggregated(field: str, value: str) -> None:
    reports = lane_engine.analyze_lanes(_bundle(), target=_bundle()["url"], lanes=["seo", "neo"])
    reports["neo"]["context"][field] = value
    with pytest.raises(ValueError, match="context"):
        build_optimization_report(reports)


def test_stale_trend_cannot_start_a_new_brief() -> None:
    result = analyze_trends(_evidence(), as_of="2026-09-07T12:00:00+00:00")
    assert result["refresh"]["needs_refresh"] is True
    assert result["freshness"]["stale_for_window"] is True
    assert result["freshness"]["stale_at_capture"] is False
    assert result["content_action"] == "refresh-before-brief"
    assert result["opportunity"]["valid_for_new_content"] is False


def test_future_capture_cannot_be_used_as_current_evidence() -> None:
    with pytest.raises(ValueError, match="future"):
        analyze_trends(_evidence(), as_of="2026-08-30T12:00:00+00:00")


@pytest.mark.parametrize("text", [
    "세종대왕은 훈민정음을 창제했습니다. 백성이 우리말을 쉽게 적도록 만든 문자입니다.",
    "보관할 때는 물기를 닦고 뚜껑을 닫으세요. 직사광선이 들지 않는 곳이 좋습니다.",
    "비가 오면 산책로 입구가 미끄럽습니다. 난간을 잡고 천천히 내려오세요.",
    "이 방법은 사진 원본을 보존합니다. 변경된 사진은 새 파일로 따로 저장됩니다.",
    "환불을 신청하려면 주문 내역에서 해당 상품을 선택하세요. 신청 사유도 적어주세요.",
    "버튼을 눌러도 화면이 바뀌지 않으면 연결 상태를 먼저 확인합니다.",
    "분갈이 직후에는 흙이 마른 뒤 물을 줍니다. 화분 아래로 물이 빠지는지 살펴보세요.",
    "사용한 자료의 출처는 본문 아래에 적었습니다. 발표일과 확인일은 구분했습니다.",
    "버스 정류장에서 골목으로 들어오면 왼쪽에 입구가 있어요.",
    "이 글은 처음 사용하는 분을 위한 안내예요. 필요한 설정부터 차근차근 살펴볼게요.",
])
def test_korean_style_is_not_penalized_for_missing_english_names(text: str) -> None:
    result = analyse(text)
    assert result["information_density"] is None
    assert "low-density" not in result["flags"]
    assert "thin-content" not in result["flags"]
    assert result["semantic_quality"] == "unmeasured"
    assert result["score_kind"] == "style-diagnostics"
    assert analyse(text + " 42 56 87")["overall_quality"] == result["overall_quality"]


def test_repeated_korean_text_still_receives_a_style_warning() -> None:
    result = analyse("근거 없이 같은 문장을 반복합니다. " * 50)
    assert "repetitive" in result["flags"]


def test_context_roundtrip_does_not_modify_input() -> None:
    bundle = _bundle()
    original = copy.deepcopy(bundle)
    lane_engine.analyze_lanes(bundle, target=bundle["url"], lanes=["seo", "neo"])
    assert bundle == original


def test_explicit_reviews_require_matching_text_and_source_provenance() -> None:
    bundle = _bundle()
    review = {"status": "pass", "page_url": bundle["url"], "collected_at": bundle["collected_at"],
              "reviewed_at": bundle["collected_at"], "reviewer": "codex",
              "excerpt": bundle["content"]["text"], "reason": "This passage answers the supplied question."}
    bundle["review_evidence"] = {"direct_answer": review, "claim_source_support": copy.deepcopy(review)}
    assert _checks(bundle, "aeo")["direct_answer"]["status"] == "pass"
    assert _checks(bundle, "aeo")["claim_source_support"]["status"] == "unmeasured"
    review["excerpt"] = "not in this page"
    assert _checks(bundle, "aeo")["direct_answer"]["status"] == "unmeasured"


def test_crawler_observations_are_page_bound_dated_and_not_index_directives() -> None:
    bundle = _bundle()
    bundle["site_evidence"] = {"origin": "https://example.com", "page_url": bundle["url"],
        "observed_at": bundle["collected_at"], "checks": {
            "googlebot": {"allowed": False, "url": "https://example.com/robots.txt", "detail": "Disallow: /guide"},
            "Yeti": {"allowed": True, "url": "https://example.com/robots.txt", "detail": "Allow: /"}}}
    assert _checks(bundle, "seo")["googlebot_policy"]["status"] == "fail"
    assert _checks(bundle, "seo")["index_eligible"]["status"] == "pass"
    assert _checks(bundle, "neo")["yeti_policy"]["status"] == "pass"
    bundle["site_evidence"]["page_url"] = "https://example.com/different"
    assert _checks(bundle, "neo")["yeti_policy"]["status"] == "unmeasured"


def test_duplicate_checks_cannot_inflate_the_score() -> None:
    check = {"id": "title", "status": "pass", "severity": "low"}
    with pytest.raises(ValueError, match="duplicate"):
        lane_engine.score_checks([check, check])


def test_search_comparison_refuses_different_markets_and_missing_context(monkeypatch) -> None:
    import search_evidence
    monkeypatch.setattr(search_evidence, "validate_url", lambda _: True)
    sample = {"schema_version": 1, "query": "한국어 가이드", "captured_at": "2026-08-28T00:00:00Z",
              "market": "KR", "language": "ko", "device": "desktop", "surface": "naver-web",
              "method": "manual-sample-v1", "window": "snapshot", "sample_limit": 10,
              "results": [{"position": 1, "url": "https://example.com/", "title": "가이드", "result_type": "organic"}]}
    current = copy.deepcopy(sample)
    current["captured_at"] = "2026-08-29T00:00:00Z"
    assert search_evidence.compare(sample, current)["comparable"] is True
    current["market"] = "US"
    result = search_evidence.compare(sample, current)
    assert result["comparable"] is False and result["competition_proxy_change"] is None
