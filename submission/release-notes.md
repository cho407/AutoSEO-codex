# AutoSEO 0.4.0-rc.1

Free, local-first release candidate with independent SEO, AEO, GEO, LLMO, and
NEO lanes plus guarded PC Naver Blog SmartEditor ONE automation.

## Added

- `EvidenceBundle v1`: one HTTP collection and at most one render per URL and audit
- One reused Chromium instance for all pages that actually need rendering
- Deterministic lane selection and independent `LaneReport v1` readiness scoring
- Korean NFKC normalization, Hangul tokens, and information/commercial/local/
  transactional intent classification
- Optional free Naver Search verticals and DataLab evidence from environment keys
- Bounded Naver AI Briefing observation samples with source/outcome separation
- `NaverDocument v1`, complete editor feature registry, local UI learning map,
  operation checkpoints, stale-element recovery, and resume without duplicate blocks
- Dedicated headed Naver profile with manual login, two-factor authentication,
  and CAPTCHA
- Document-bound draft approval and fresh per-post publish/schedule approval
- Runtime profiles for `lite`, `standard`, optional `google`, and optional `report`
- Reproducible 20-page collection benchmark and editor safety regression suite

## Changed

- GEO crawler guidance now separates OAI-SearchBot from GPTBot and
  PerplexityBot from Perplexity-User.
- Universal citation word counts, universal JavaScript claims, `llms.txt` ranking
  weight, artificial mention-building, and AI-specific sentence splitting no longer
  affect readiness scores.
- Missing evidence is `unmeasured`; it is not converted to zero.
- Observed ranks, clicks, citations, and answer samples stay outside readiness scores.
- CI now runs a single Python 3.12 PR/main validation plus a clean `git archive`
  check. Python 3.10 and 3.14 compatibility runs only for tags or manual releases.

## Safety and limits

- No paid dataset, subscription API, hosted backend, or telemetry is included.
- Local cache is opt-in, public-page-only, and expires after 24 hours.
- Naver browser profiles and checkpoints use owner-only permissions; cookies and
  article bodies are not exported or stored in checkpoints.
- Ambiguous UI stops without guessing. An unclear publication result is never retried.
- Automated tests disable Naver publish/schedule before any mutation.
- Bulk posts, automatic comments/sympathy/neighbors, login bypass, Cafe, Place,
  Smart Store, and mobile editors are out of scope.
- Rankings, indexation, citations, model learning, and Naver exposure are not guaranteed.

## Release-candidate gate

The full automated suite and clean release archive must pass before tagging. Promote
to `0.4.0` only after a user-owned live Naver draft verifies ordinary formatting,
media, advanced components, draft save, separately approved publish, and separately
approved schedule once each. Until then the feature classifications document
implemented and mock-verified behavior, not a live-platform guarantee.
