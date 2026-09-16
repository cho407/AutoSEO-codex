# Overall and category trend collection

This is an on-demand, read-only workflow. Do not schedule daily jobs, draft articles,
install dependencies, log in to a service or publish merely because trends were
requested. Use the existing AutoSEO runtime; if unavailable, explain the missing
setup and ask before installing. Native Codex web research runs in the user's
existing session, not a separate paid search API.

## Scope and natural requests

- Default to market `KR`, language `ko`, window `24h` unless the user/context says
  otherwise. For sustained topics use `7d`; `4h`, `48h`, `30d` are available.
- “전체 트렌드 수집” means an overall sample with category groups. It does not mean
  every keyword on the internet or a full Naver realtime ranking.
- “여행 카테고리 트렌드 조사” means category-filtered RSS **plus actual current web
  research in that category**. Do not stop after returning a plan or filtering a
  short global feed. “수집만” can explicitly skip supplementary web research.
- Reuse known blog categories when relevant; never force an unrelated headline
  into the author's subject. Ask only if an ambiguous category materially changes
  scope. Use `--keyword` for custom topics not covered by the catalog.
- `categories` lists 14 local categories: IT/technology/appliances, economy/business,
  travel, food, beauty/fashion, parenting/education, health/exercise, lifestyle/shopping,
  entertainment, sports, culture/games, politics, society/local and world.
  Korean aliases such as `여행`, `경제`, `육아`, `IT` resolve to stable IDs.
- Select up to four categories in one bounded pass; `all` alone includes all groups.
  Repeated `--keyword` values are OR filters, exclusions win, and category filters
  are OR filters. Keyword/exclusion filters apply to keyword + source headlines;
  category filters require a keyword-level rule or an explicit reviewed assignment.

## Execute, not just propose

1. For category research (or explicit overall research), generate the bounded query
   plan. It creates **unexecuted** suggestions, two queries per selected category,
   at most eight. Run those queries with the available Codex web tool, inspect the
   primary announcements/reports and useful independent coverage, and adjust overly
   broad queries within the same total budget. Record the actual queries used.
2. Keep at most 20 inspected URLs per query and 100 observations total. Verify page
   publication dates; date filters/search snippets alone are not date verification.
   Distinguish event dates from publication dates. If a source has no reliable
   date, exclude it from fresh observations and mention the evidence gap. Do not
   invent a timestamp to pass the validator. A date-only source can be represented
   conservatively as the start of its explicitly known source-local date with
   `published_precision: day`; disclose that precision limit, and omit it if its
   inclusion at the window boundary is uncertain. Omitted precision means a verified
   timestamp, not a guessed time.
3. Write the actual inspected observations as `TrendResearch v1` in a temporary or
   user-approved local output location. Use the schema and example as structure
   only: `examples/trend-research-v1.json` is fictional, never live evidence.
   Every observation must point to a URL recorded under its actual query. Scope
   market/language/window must match collection. Category assignment requires a
   short reason and is marked `reviewed-category`, not provider-certified.
4. Run collection once, attaching that research file. It fetches the market's
   official Google RSS once for every requested category together, normalizes and
   deduplicates observations, filters dates/categories/keywords, and reports groups.
   For overall collection alone, run `collect` directly without a research file.
5. Return a compact category table and candidates with source links, dates,
   `demand_status`, classification reason and limits. Report excluded/stale data,
   unavailable providers and empty categories. Preserve unknown demand as unknown.
   An empty RSS category can still have researched current topics; those remain
   `unmeasured` unless a genuine demand observation exists.

```text
<plugin-root>/scripts/autoseo run trend_collect.py categories
<plugin-root>/scripts/autoseo run trend_collect.py plan --category 여행 --category IT --window 24h
<plugin-root>/scripts/autoseo run trend_collect.py collect --market KR
<plugin-root>/scripts/autoseo run trend_collect.py collect --category 여행 --category IT --research-input <research.json>
<plugin-root>/scripts/autoseo run trend_collect.py collect --keyword 캠핑 --keyword 텐트 --exclude 사고 --window 7d --output <collection.json>
```

Output is JSON on stdout by default; `--output` explicitly saves an owner-only
JSON file, refusing overwrites unless `--overwrite` is supplied. Keep research
artifacts out of the plugin source and Git. `--rss-file <snapshot.xml>` replaces
the network call for reproducible/offline inspection and is labeled `supplied-rss`.
`--as-of` is for explicit historical evaluation/testing, never a way to label old
observations as live. No cookies, credentials, profile or article body is collected.

## Read the evidence correctly

- `observed-surge-single-provider`: present in the supplied/current Google RSS
  snapshot within the chosen date window. A search surge, not confirmed continued
  growth, a Naver signal or a proven writing opportunity. Feed order is not ranking.
- `unmeasured`: dated topic found in inspected primary/news sources, with no measured
  search demand. Several reports can verify an event, not manufacture search volume.
- Traffic buckets such as `1,000+` remain raw buckets. Never convert them to exact
  counts, 0–100 opportunity/velocity scores or forecasts. Separate relative Explore
  interest from growth rates; compare metrics only within matching methods/scopes.
- Category rules are transparent local heuristics and may miss entities or classify
  multiple categories. Review ambiguous candidates; `uncategorized` is retained in
  overall results. No official category-specific RSS endpoint is assumed.
  `category_hints` holds context-only matches and is not used for category filtering:
  a celebrity headline mentioning travel must not automatically become a travel
  keyword. Promote a hint only after inspecting relevance and recording a reason
  in the research observation's category assignment.
- The RSS is a limited snapshot, not a history archive; choosing `7d`/`30d` only
  filters available evidence and does not backfill days. Google describes roughly
  ten-minute Trending Now updates, not a guaranteed RSS freshness SLA. Show actual
  collection and feed dates. Re-run when `refresh_after` is reached.
- `research_plan.status=not-run` remains a plan; `research_queries` records actual
  imported observations separately. If the web tool is unavailable, say research
  was not run, return only the feed sample, and keep its coverage limitations.
  Old imported queries retain their original refresh deadline; a new RSS fetch
  cannot make stale research fresh. Refresh stale research before drafting.
- Do not use undocumented private APIs, scrape logged-in Creator Advisor, or route
  to a billable Naver API HUB endpoint. Public third-party UIs and free logins do not
  automatically grant an automation API. No third-party subscription is required.

Before writing: select a relevant candidate, inspect and corroborate original facts,
normalize those sources as `TrendEvidence v1`, and respect its current-time refresh
gate. A collection request ends with research results; article creation requires
the user's writing request. Sensitive medical/financial/legal topics require
appropriate primary-source checks and must not become speculative advice.

Official references:

- [Google Trending Now and RSS/export](https://support.google.com/trends/answer/3076011?hl=en)
- [Related searches: top vs rising](https://support.google.com/trends/answer/4355000?hl=en)
- [Google Trends API limited access](https://developers.google.com/search/apis/trends)
