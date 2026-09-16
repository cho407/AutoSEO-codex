from __future__ import annotations

import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "autoseo" / "scripts"))

import trend_collect as trends  # noqa: E402

NOW = "2026-09-16T06:00:00+00:00"


def rss(*items: tuple[str, str, str]) -> bytes:
    rows = "".join(
        f"<item><title>{title}</title><pubDate>{date}</pubDate>"
        f"<ht:approx_traffic>1,000+</ht:approx_traffic><ht:news_item>"
        f"<ht:news_item_title>{headline}</ht:news_item_title>"
        f"<ht:news_item_url>https://example.com/{index}</ht:news_item_url>"
        "</ht:news_item></item>"
        for index, (title, date, headline) in enumerate(items)
    )
    return (
        '<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>'
        + rows
        + "</channel></rss>"
    ).encode()


FRESH = "Wed, 16 Sep 2026 04:00:00 +0000"
FEED = rss(
    ("제주 여행", FRESH, "제주 가을 축제 여행 정보"),
    ("AI 반도체", FRESH, "AI 기술과 반도체 산업 발표"),
    ("Chair festival", FRESH, "A new annual event"),
    ("제주 여행", FRESH, "제주 여행 새 소식"),
)


def research() -> dict:
    return {
        "schema_version": 1,
        "kind": "TrendResearch",
        "market": "KR",
        "language": "ko",
        "window": "24h",
        "queries": [
            {
                "query": "대한민국 여행 최신 발표",
                "searched_at": NOW,
                "urls": ["https://example.org/autumn?utm_source=test"],
            }
        ],
        "observations": [
            {
                "keyword": "가을 지역 축제",
                "title": "가을 축제 일정 공식 발표",
                "url": "https://example.org/autumn",
                "source_type": "primary-source",
                "published_at": "2026-09-16T03:00:00+00:00",
                "observed_at": NOW,
                "query": "대한민국 여행 최신 발표",
                "categories": ["travel"],
                "category_reason": "여행객 대상 축제 일정 발표",
            }
        ],
    }


def collect(**kwargs) -> dict:
    return trends.collect_trends(rss_content=FEED, as_of=NOW, **kwargs)


def test_global_collection_groups_categories_without_inventing_rank_or_volume() -> None:
    report = collect()
    assert report["kind"] == "TrendCollection"
    assert report["schema_version"] == 1
    assert report["counts"]["duplicate_observations"] == 1
    assert report["counts"]["returned"] == 3
    assert {x["id"] for x in report["groups"]} >= {"travel", "technology", "uncategorized"}
    item = report["items"][0]
    assert item["exact_search_volume"] is None
    assert item["demand_status"] == "observed-surge-single-provider"
    assert item["evidence"][0]["traffic_bucket"] == "1,000+"
    assert report["coverage"]["exhaustive"] is False
    assert "rank" not in item


def test_multiple_categories_aliases_keywords_and_exclusions_share_one_fetch() -> None:
    fetch = Mock(return_value=FEED)
    report = trends.collect_trends(
        categories=["여행", "IT"],
        keywords=["제주", "반도체"],
        exclude=["반도체"],
        as_of=NOW,
        fetcher=fetch,
    )
    fetch.assert_called_once_with("KR")
    assert [x["keyword"] for x in report["items"]] == ["제주 여행"]
    assert report["scope"]["categories"] == ["travel", "technology"]


def test_ascii_category_terms_use_word_boundaries_and_korean_is_normalized() -> None:
    assert trends.classify("chair repair") == []
    assert "technology" in {x["id"] for x in trends.classify("ＡＩ 반도체")}
    assert "travel" in {x["id"] for x in trends.classify("제주여행")}


def test_incidental_headline_words_do_not_make_a_celebrity_a_travel_keyword() -> None:
    feed = rss(("어떤 연예인", FRESH, "배우, 여행 중 환한 미소"))
    overall = trends.collect_trends(rss_content=feed, as_of=NOW)
    assert {x["id"] for x in overall["items"][0]["categories"]} == {"entertainment"}
    assert "travel" in {x["id"] for x in overall["items"][0]["category_hints"]}
    selected = trends.collect_trends(rss_content=feed, categories=["여행"], as_of=NOW)
    assert selected["items"] == []
    assert selected["counts"]["needs_category_review"] == 1


def test_empty_category_is_not_filled_with_unrelated_global_results() -> None:
    report = collect(categories=["육아"])
    assert report["items"] == []
    assert report["groups"][0]["id"] == "parenting"
    assert report["groups"][0]["count"] == 0
    assert report["coverage"]["research_status"] == "not-run"
    assert report["research_plan"]["queries"]


def test_duplicate_order_does_not_discard_the_newest_observation() -> None:
    feed = rss(
        ("제주 여행", "Wed, 16 Sep 2026 01:00:00 +0000", "여행"), ("제주 여행", FRESH, "여행")
    )
    report = trends.collect_trends(rss_content=feed, as_of=NOW)
    assert report["items"][0]["newest_at"] == "2026-09-16T04:00:00+00:00"


def test_stale_missing_and_future_dates_are_excluded_not_relabelled_live() -> None:
    feed = rss(
        ("옛 여행", "Mon, 14 Sep 2026 04:00:00 +0000", "여행"),
        ("미래 여행", "Thu, 17 Sep 2026 04:00:00 +0000", "여행"),
        ("날짜 없음", "not a date", "여행"),
    )
    report = trends.collect_trends(rss_content=feed, as_of=NOW)
    assert report["items"] == []
    assert report["counts"]["excluded"] == {"stale": 1, "future": 1, "invalid": 1}


def test_research_adds_category_topics_without_claiming_measured_demand() -> None:
    value = research()
    value["observations"].append(copy.deepcopy(value["observations"][0]))
    report = collect(categories=["travel"], research=value)
    assert report["coverage"]["research_status"] == "collected"
    item = next(x for x in report["items"] if x["keyword"] == "가을 지역 축제")
    assert item["demand_status"] == "unmeasured"
    assert item["exact_search_volume"] is None
    assert len(item["evidence"]) == 1
    assert any(c["method"] == "reviewed-category" for c in item["categories"])
    assert item["evidence"][0]["url"] == "https://example.org/autumn"
    assert report["counts"]["duplicate_observations"] == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x.update(market="US"),
        lambda x: x["observations"][0].update(url="http://127.0.0.1/private"),
        lambda x: x["observations"][0].update(url="https://example.net/not-inspected"),
        lambda x: x["observations"][0].update(metrics={"search_volume": 10000}),
        lambda x: x["observations"][0].update(published_at="2026-09-16T03:00:00"),
        lambda x: x["observations"][0].update(category_reason=""),
        lambda x: x["observations"][0].update(source_type=[]),
        lambda x: x["observations"][0].update(published_precision=[]),
    ],
)
def test_research_requires_matching_scope_inspected_public_sources_and_dated_evidence(
    mutate,
) -> None:
    value = research()
    mutate(value)
    with pytest.raises(ValueError):
        collect(research=value)


def test_provider_failure_retains_valid_research_and_does_not_leak_error_text() -> None:
    fetch = Mock(side_effect=requests.RequestException("secret-bearing upstream error"))
    report = trends.collect_trends(research=research(), fetcher=fetch, as_of=NOW)
    assert len(report["items"]) == 1
    assert report["status"] == "partial"
    assert report["sources"][0]["status"] == "unavailable"
    assert "secret-bearing" not in json.dumps(report)


def test_old_research_does_not_get_a_new_freshness_lease_from_a_live_feed() -> None:
    value = research()
    value["queries"][0]["searched_at"] = "2026-09-16T03:30:00+00:00"
    value["observations"][0]["observed_at"] = "2026-09-16T03:30:00+00:00"
    report = collect(research=value)
    assert report["coverage"]["research_status"] == "stale"
    assert report["refresh_after"] < NOW
    assert report["counts"]["research_observations"] == 1


def test_day_precision_is_preserved_instead_of_implying_an_exact_publication_time() -> None:
    value = research()
    value["observations"][0]["published_precision"] = "day"
    value["observations"][0]["published_at"] = "2026-09-16T00:00:00+09:00"
    report = collect(research=value)
    item = next(x for x in report["items"] if x["keyword"] == "가을 지역 축제")
    assert item["evidence"][0]["published_precision"] == "day"
    value["observations"][0]["published_precision"] = "guessed"
    with pytest.raises(ValueError, match="precision"):
        collect(research=value)


def test_output_limit_and_local_symlink_guard(tmp_path) -> None:
    report = collect(limit=1)
    assert report["counts"]["truncated"] is True
    assert report["counts"]["matched"] == 3
    assert len(report["items"]) == 1
    feed = tmp_path / "feed.xml"
    feed.write_bytes(FEED)
    existing = tmp_path / "existing.json"
    existing.write_text("unchanged")
    link = tmp_path / "link.json"
    link.symlink_to(existing)
    with pytest.raises(SystemExit):
        trends.main(
            [
                "collect",
                "--rss-file",
                str(feed),
                "--as-of",
                NOW,
                "--output",
                str(link),
                "--overwrite",
            ]
        )
    assert existing.read_text() == "unchanged"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": float("nan")},
        {"limit": True},
        {"market": "KR&category=1"},
        {"categories": ["not-real"]},
        {"categories": ["all", "travel"]},
        {"window": "1y"},
    ],
)
def test_invalid_options_fail_before_any_network_call(kwargs) -> None:
    fetch = Mock(return_value=FEED)
    with pytest.raises(ValueError):
        trends.collect_trends(fetcher=fetch, as_of=NOW, **kwargs)
    fetch.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE rss [<!ENTITY x "payload">]><rss><channel/></rss>',
        "<!DOCTYPE rss><rss/>".encode("utf-16"),
        b"<html>Login required</html>",
        b"x" * (2 * 1024 * 1024 + 1),
    ],
)
def test_unsafe_or_non_rss_inputs_are_rejected(payload: bytes) -> None:
    with pytest.raises(ValueError):
        trends.parse_google_rss(payload)


def test_fetch_is_bounded_cookie_free_and_does_not_follow_redirects(monkeypatch) -> None:
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.content = FEED

    @contextmanager
    def pinned(url):
        assert url == "https://trends.google.com/trending/rss?geo=KR"
        yield session

    monkeypatch.setattr(trends, "safe_requests_session", pinned)
    limited = Mock(return_value=session.get.return_value)
    monkeypatch.setattr(trends, "read_limited_response", limited)
    assert trends.fetch_google_trends("KR") == FEED
    assert session.trust_env is False
    session.cookies.clear.assert_called_once()
    assert session.get.call_args.kwargs["allow_redirects"] is False
    limited.assert_called_once_with(session.get.return_value, max_bytes=2 * 1024 * 1024)
    session.get.return_value.status_code = 302
    with pytest.raises(ValueError, match="status"):
        trends.fetch_google_trends("KR")


def test_plan_is_dated_bounded_and_not_misrepresented_as_executed() -> None:
    plan = trends.research_plan(categories=["여행", "경제"], as_of=NOW)
    assert 2 <= len(plan["queries"]) <= 8
    assert plan["status"] == "not-run"
    assert plan["scope"]["categories"] == ["travel", "economy"]
    assert all("after:" in row["query"] for row in plan["queries"])


def test_cli_offline_output_and_overwrite_guard(tmp_path, capsys) -> None:
    feed = tmp_path / "feed.xml"
    feed.write_bytes(FEED)
    output = tmp_path / "report.json"
    args = ["collect", "--rss-file", str(feed), "--as-of", NOW, "--output", str(output)]
    assert trends.main(args) == 0
    assert json.loads(output.read_text())["counts"]["returned"] == 3
    with pytest.raises(SystemExit):
        trends.main(args)
    capsys.readouterr()


def test_shipped_research_example_is_valid_and_unknown_values_remain_unmeasured() -> None:
    root = ROOT / "plugins" / "autoseo"
    data = json.loads((root / "examples" / "trend-research-v1.json").read_text())
    report = trends.collect_trends(
        rss_content=rss(),
        research=data,
        as_of=data["queries"][0]["searched_at"],
    )
    assert report["items"][0]["demand_status"] == "unmeasured"
    schema = json.loads((root / "schema" / "trend-research.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == 1
