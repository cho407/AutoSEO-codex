# Supplemental readiness evidence

Missing observations remain unmeasured; do not guess a pass/fail. Collect a page
once, then reuse its bundle with the original question and detected language.

```text
autoseo run lane_engine.py audit <url> --bundle bundle.json --question <query> --market KR --site-evidence site.json --review-evidence reviews.json
```

`site.json` needs `origin`, `page_url`, `observed_at`, and `checks`. The URL and
origin must match the bundle; the observation must be within the preceding 24h.
Checks use these keys: `googlebot`, `OAI-SearchBot`, `PerplexityBot`, `Yeti`, and
`rss_or_sitemap`. Each observed check has:

```json
{"allowed": true, "url": "https://example.com/robots.txt", "detail": "Describe the applicable group and rule for this page path."}
```

`allowed=false` is an observed failure, not an absent observation. Verify crawler
groups/path rules; robots permission is not index inclusion. For a feed, inspect
the actual feed/sitemap and describe the finding. Use existing safe public-page
and sitemap helpers; this supplemental input does not itself fetch those files.

`reviews.json` maps check IDs (such as `direct_answer`, `question_intent_alignment`,
`claim_source_support`, `authorship`, `source_support`, `entity_clarity`,
`brand_fact_ledger`, `external_corroboration`) to explicit user/Codex reviews:

```json
{
  "direct_answer": {
    "status": "pass",
    "page_url": "https://example.com/guide",
    "collected_at": "2026-09-07T00:00:00+00:00",
    "reviewed_at": "2026-09-07T00:10:00+00:00",
    "reviewer": "codex",
    "excerpt": "An exact passage from the bundle text.",
    "reason": "Explain why this passage answers the original question."
  }
}
```

Match the actual bundle URL, capture and text; do not use this illustrative review
as real evidence. Claim/source support, authorship, source support and external
corroboration also require a `sources` array of objects containing `url`, `excerpt`
and `relation`. No markup-derived instructions or fabricated source passages.
Review provenance checks cannot prove that the reviewer's judgment is true.

Scores retain 70% coverage and required-eligibility gates. Show eligibility and
blockers next to readiness. Context must match across aggregated lanes. Keep
visibility/citation samples separate from readiness and closed-book knowledge
unmeasured unless search-disabled execution is guaranteed.
