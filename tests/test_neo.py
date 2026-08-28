from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import content_quality  # noqa: E402
import naver_evidence  # noqa: E402
import search_evidence  # noqa: E402
from korean_text import classify_intent, normalize_text, tokenize  # noqa: E402


def _search_payload(query: str) -> dict:
    return {
        "schema_version": 1,
        "query": query,
        "captured_at": "2026-08-28T00:00:00+09:00",
        "market": "KR",
        "results": [
            {
                "position": 1,
                "url": "https://example.com/result",
                "title": query,
                "result_type": "organic",
            }
        ],
    }


def test_korean_nfkc_tokens_and_intents() -> None:
    assert normalize_text("ＡＩ\u00a0검색\n방법") == "AI 검색 방법"
    assert tokenize("네이버 AI 브리핑 작성 방법") == [
        "네이버",
        "ai",
        "브리핑",
        "작성",
        "방법",
    ]
    assert classify_intent("네이버 AI 브리핑은 무엇인가요")["primary"] == "informational"
    assert classify_intent("서울 근처 피부과 위치")["primary"] == "local"
    assert classify_intent("노트북 가격 비교 후기")["primary"] == "commercial"
    assert classify_intent("온라인으로 예약 신청하기")["primary"] == "transactional"


def test_korean_content_no_longer_has_zero_tokens_or_english_fallback_intent() -> None:
    quality = content_quality.analyse(
        "네이버 검색 사용자가 궁금해하는 질문에 근거와 실제 사례로 답합니다. " * 30
    )
    assert quality["tokens"] > 0
    assert quality["unique_tokens"] > 3

    informational = search_evidence.analyze(_search_payload("여권 갱신 방법은 무엇인가요"))
    transactional = search_evidence.analyze(_search_payload("호텔 예약 신청하기"))
    assert informational["intent"] == "informational"
    assert transactional["intent"] == "transactional"


def test_naver_search_client_uses_environment_keys_without_returning_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "client-id-secret")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "client-secret-value")
    captured: dict = {}

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "total": 1,
                "start": 1,
                "display": 1,
                "items": [
                    {
                        "title": "<b>검색</b> 결과",
                        "description": "무료 공개 결과",
                        "link": "https://example.com/post",
                    }
                ],
            }

        @staticmethod
        def raise_for_status() -> None:
            pass

    def fake_get(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    result = naver_evidence.search(
        "검색 방법", vertical="blog", display=10, request_get=fake_get
    )

    assert captured["url"] == "https://openapi.naver.com/v1/search/blog.json"
    assert captured["headers"] == {
        "X-Naver-Client-Id": "client-id-secret",
        "X-Naver-Client-Secret": "client-secret-value",
    }
    serialized = repr(result)
    assert "client-id-secret" not in serialized
    assert "client-secret-value" not in serialized
    assert result["items"][0]["title"] == "검색 결과"
    assert result["subscription_required"] is False


def test_naver_api_rejects_missing_keys_and_unknown_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    with pytest.raises(ValueError, match="environment variables"):
        naver_evidence.search("검색", vertical="blog")
    with pytest.raises(ValueError, match="vertical"):
        naver_evidence.search("검색", vertical="news-paywalled")


def test_naver_datalab_returns_relative_trends_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "datalab-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "datalab-secret")
    captured: dict = {}

    class Response:
        @staticmethod
        def raise_for_status() -> None:
            pass

        @staticmethod
        def json() -> dict:
            return {"results": [{"title": "검색", "data": [{"ratio": 100}]}]}

    def fake_post(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    result = naver_evidence.datalab_search(
        [{"groupName": "검색", "keywords": ["네이버 검색", "검색 방법"]}],
        start_date="2026-08-01",
        end_date="2026-08-28",
        request_post=fake_post,
    )

    assert captured["url"] == "https://openapi.naver.com/v1/datalab/search"
    assert result["exact_search_volume"] is None
    assert result["subscription_required"] is False
    assert "datalab-secret" not in repr(result)


def test_ai_briefing_sample_is_bounded_and_dimensioned() -> None:
    sample = {
        "schema_version": 1,
        "query": "운전면허 갱신 구비서류",
        "market": "KR",
        "language": "ko",
        "captured_at": "2026-08-28T09:00:00+09:00",
        "surface": "official",
        "observed": True,
        "sources": [
            {"url": "https://www.gov.kr/example", "target": True},
            {"url": "https://example.com/guide", "target": False},
        ],
    }
    summary = naver_evidence.summarize_ai_briefing_samples([sample])

    assert summary["sample_count"] == 1
    assert summary["observations"][0]["numerator"] == 1
    assert summary["observations"][0]["denominator"] == 2
    for key in (
        "market",
        "language",
        "surface",
        "measured_at",
        "confidence",
        "limitations",
    ):
        assert key in summary["observations"][0]

    with pytest.raises(ValueError, match="25"):
        naver_evidence.summarize_ai_briefing_samples([sample] * 26)
