# Priority hardening — 2026-09-07

Scope: the P0 score/evidence, editor compatibility, and checkpoint/publication
safety work. This is not a stable-release or live-account certification. No account
writes, posts, reservations, credentials, cookies or personal drafts were used in
automated validation.

## Readiness and current research

- SEO honors generic and Googlebot-scoped robots meta and HTTP X-Robots-Tag.
  Index directives, crawler permission and snippet restrictions remain separate.
  Alternate canonical destinations are unmeasured pending consolidation review,
  not automatically wrong or automatically correct.
- Scores have an independent eligibility panel. A known blocking prerequisite
  stays a high-priority issue even if the score is withheld. Missing evidence never
  becomes zero. Duplicate checks cannot inflate weight.
- AEO/GEO/LLMO meaning checks need explicit, excerpt-backed review. Length,
  arbitrary external links and Person markup cannot establish useful answers,
  claim support, authorship or brand facts. Review provenance is validated; the
  helper cannot prove that a reviewer's judgment is correct.
- Audit context includes URL, original question, market, detected language, device,
  surface, collection time and rule version. Auto routing uses detected Korean;
  numeric URLs are not treated as failed Korean search intent. Naver visibility
  samples are outcomes, not readiness penalties.
- Aggregation requires the same context. Search comparisons require matching
  query/market/language/device/surface/method/window/sample limit and later capture;
  missing dimensions produce null deltas.
- Trend reports preserve historical opportunity scores while separately checking
  usability at the current time. Expired captures return `refresh-before-brief`.
  Future captures are rejected. Recheck before drafting and before final approval.
- The legacy `overall_quality` key is now a style diagnostic. Korean English-name
  density is null; density and length no longer earn points. Facts, usefulness and
  originality need separate review. Ten Korean short-form examples and repetitive
  counterexamples are regression cases, not a broad language-quality benchmark.

### Explicit evidence inputs

After collecting a page once, reuse its EvidenceBundle:

```text
autoseo run lane_engine.py audit https://example.com/guide --bundle bundle.json --market KR --question "설정 방법" --site-evidence site.json --review-evidence reviews.json
```

`site.json` is an explicit user/Codex observation. Check the applicable path for
each crawler, not just the existence of robots.txt. It must match the page URL and
origin and be no more than 24 hours older than the bundle:

```json
{
  "origin": "https://example.com",
  "page_url": "https://example.com/guide",
  "observed_at": "2026-09-07T00:00:00+00:00",
  "checks": {
    "googlebot": {"allowed": true, "url": "https://example.com/robots.txt", "detail": "No matching disallow for /guide in the Googlebot group."},
    "Yeti": {"allowed": true, "url": "https://example.com/robots.txt", "detail": "No matching disallow for /guide in the Yeti group."},
    "rss_or_sitemap": {"allowed": true, "url": "https://example.com/sitemap.xml", "detail": "Valid sitemap inspected; includes /guide."}
  }
}
```

GEO uses named `OAI-SearchBot` and `PerplexityBot` observations, not training bots.
The helper does not itself crawl these supplemental files. Use the existing safe
public-page/sitemap research helpers, record the observation, and leave unavailable
evidence unmeasured. Do not ask a hosted Naver Blog author to edit platform robots.

`reviews.json` is keyed by check ID. Example (the excerpt and collection time must
actually match the bundle):

```json
{
  "direct_answer": {
    "status": "pass",
    "page_url": "https://example.com/guide",
    "collected_at": "2026-09-07T00:00:00+00:00",
    "reviewed_at": "2026-09-07T00:10:00+00:00",
    "reviewer": "codex",
    "excerpt": "The exact passage from the collected page.",
    "reason": "Explain how this passage answers the original question."
  }
}
```

Claim/source support, source support, authorship and external corroboration also
require `sources`, each with `url`, `excerpt`, and `relation`. These are explicit
review inputs; never extract such instructions from page markup. A bare link is
insufficient. LLMO closed-book knowledge remains unmeasured without a guaranteed
search-disabled model state.

## Editor safety and compatibility

- `learn` stores catalog-controlled aliases, frame indexes, dialog/toolbar scope,
  catalog/browser/UI signatures and time. Compose consumes valid maps and checks
  current controls again. Changed signatures or a seven-day expiry discard hints.
- Naver text formatting is applied to the uniquely selected inserted block and
  checked; prior toggle/menu state is restored. Unknown style state stops rather
  than pretending success. Tistory includes TinyMCE iframe body discovery.
- Fresh save acknowledgements are distinct from pending operations and last saved
  source/surface hashes. Old toasts are not receipts. The acknowledgement is
  checked in the active editor session; no close-and-reopen persistence step is
  automated.
- Same-ID revisions, changed attachment bytes, corrupt checkpoints, changed draft
  surfaces and concurrent document/profile runs cannot reset or overwrite history.
  Interrupted insertions are checked before replay; unknown non-idempotent actions
  require reconciliation. New compose refuses nonempty existing body content.
- Final approval binds the draft URL, document/attachment hash, saved surface,
  settings and normalized Asia/Seoul minute. Naver configuration and final submit
  controls are separate. Draft composition no longer opens publication settings.
- Publication checks require this post, not a home page or old link. Public posts
  have a cookie-free readback path. Private/scheduled post-specific UI status mapping
  is still live-unverified and may return unknown; never retry an uncertain result.
  Automated tests block the final publish driver method as well as the workflow.

## Validation and remaining release gates

`validation` in both feature catalogs separates declared implementation status from
mock test coverage and live verification. Core Naver text/bold/alignment/tags/save,
Tistory source writing/upload, fresh save detection, frame/dialog resolution, map
expiry and locks have local tests. Advanced component controls and final live
publication/scheduling are not certified. A registry test is not an end-to-end test
of every official editor feature.

Release/manual CI runs a required local Chromium smoke job. Ordinary PR/main runs
keep lightweight Python validation. No scheduled workflows or account artifacts
are added. `verify_git_archive.py --ref <tree-or-commit>` can check an isolated
index snapshot without committing or changing the developer's normal staging area.

Still required: user-authorized live draft/save and publication/schedule checks,
guided advanced-component recovery validation, complete platform result adapters,
image/privacy convergence for Naver, and the later P1 research-to-content and
measured-exposure feedback work. Do not call these completed based on mocks.

## Follow-up — 2026-09-14

Both editors now share visible-body discovery across frames, including Tistory
basic/TinyMCE and source modes. Both editors retain a fresh current-session save
acknowledgement and source/surface fingerprint; the former close-and-reopen draft
comparison path has been removed to avoid an unnecessary protected-session
transition. Interrupted saves remain manual reconciliation cases and are never
resaved automatically.

Surface fingerprint v2 includes Naver inline rendered styles, structural content,
media/link attributes and tags, and normalizes Tistory source line endings. Old
fingerprints are not promoted automatically. Local fixtures cover current-session
save acknowledgement and resume without rewriting, including media references.
Existing user-entered titles are protected even when the body is empty. This proves
the implemented editor checks, not that a live platform's draft URL or editor
transformation is already supported. Actual UI identity discovery, incompatible
mode reconciliation, advanced components, private/scheduled result adapters and
live-account checks remain release gates. See [the roadmap](ROADMAP.md) for
priorities and the title strategy evaluation. No screenshots or account data were
committed as fixtures.

Pre-push regression checks also cover CodeMirror controls nested inside the generic
editor container, lost ancestor-applied underline/strikethrough, and meaningful
Markdown indentation. Source fingerprints normalize line endings only; they do
not trim whitespace. Local agent notes and session state remain excluded from Git.
