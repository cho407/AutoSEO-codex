# AutoSEO Architecture

AutoSEO is a Skills-only Codex plugin. Codex selects focused workflows while
deterministic helpers collect bounded evidence, normalize it once, and run pure
analysis over versioned contracts.

## Components

| Layer | Responsibility | Location |
|---|---|---|
| Plugin metadata | Identity, listing metadata, assets, skill discovery | `plugins/autoseo/.codex-plugin/` |
| Orchestration | Intent routing, audit policy, evidence and consent rules | `plugins/autoseo/skills/autoseo/` |
| Focused skills | Technical, content, GEO, local, commerce, and integration workflows | `plugins/autoseo/skills/` |
| Runtime boundary | Explicit setup, isolated environment, script allowlist | `plugins/autoseo/scripts/runtime.py` |
| Deterministic helpers | URL safety, crawling, parsing, API clients, scoring, exports | `plugins/autoseo/scripts/` |
| Static knowledge | Schemas, templates, update records, and skill references | `plugins/autoseo/schema/`, `data/`, and skill-local folders |
| Naver editor boundary | Versioned document, local feature map, checkpointed Playwright adapter | `naver_document.py`, `naver_editor.py`, `data/naver-editor-features.json` |
| Tistory editor boundary | Markdown/HTML document, privacy derivatives, hosted-media map, checkpointed Playwright adapter | `tistory_document.py`, `tistory_editor.py`, `privacy_mosaic.py` |

## Request flow

1. Codex routes the request and selects SEO by default for a URL, then adds AEO,
   GEO, LLMO, or NEO from topic, brand, market, language, and explicit intent.
2. The collector performs low-cost HTTP first, decides whether the response is a
   sparse application shell, and renders only when required.
3. One audit permits one raw request and at most one render per canonical URL.
   A single Chromium instance is reused across rendered pages.
4. The collector emits `EvidenceBundle v1`; all selected lanes analyze that same
   bounded record without another page request.
5. Each lane emits `LaneReport v1` with pass/fail/unmeasured checks, coverage,
   readiness, observations, confidence, and limitations.
6. Findings include evidence, severity, impact, recommendation, and confidence.
   Existing files and external systems are not changed without explicit approval.

```text
URL(s) -> safe HTTP -> SPA decision -> optional shared render -> EvidenceBundle v1
                                                        |-> SEO LaneReport v1
                                                        |-> AEO LaneReport v1
                                                        |-> GEO LaneReport v1
                                                        |-> LLMO LaneReport v1
                                                        `-> NEO LaneReport v1
```

Readiness and observed outcomes are separate. A lane shows a 0-100 score only
when required eligibility was measured and at least 70% of applicable evidence is
available. Missing evidence stays `unmeasured` rather than becoming a failure.

## Runtime lifecycle

The repository itself has no import-time installer. `autoseo doctor` is read-only.
Only an explicit `autoseo setup` creates an isolated Python environment in a dedicated
AutoSEO data directory and installs a reviewed profile:

- `lite`: core analysis without a browser;
- `standard`: core analysis plus Playwright;
- `google`: optional Google integrations;
- `image`: optional local Pillow/OpenCV privacy processing;
- `report`: optional PDF and spreadsheet tooling.

Bundled helpers are addressed by basename and must appear in `ALLOWED_CORE_SCRIPTS`.
Path separators, traversal segments, unknown scripts, extension loaders, and the
runtime module itself are rejected.

## Evidence-source model

`data/free-sources.json` is the policy catalog for public, local, Codex-native, and
optional no-cost first-party evidence. `free_source_policy.py` rejects any catalog entry
that requires a subscription. Exact commercial metrics are not approximated under a
misleading label: relative signals carry their method, sample size, date, and limits.
No connector auto-installer or separately billable data integration is shipped.

## Naver editor boundary

Analysis and account mutation are separate skills. `NaverDocument v1` validates
the title, blocks, formatting, links, attachments, tags, and publication settings
before a visible browser opens. The editor uses a dedicated persistent profile under
`AUTOSEO_DATA_DIR`; login, two-factor authentication, and CAPTCHA stay manual.

The local feature registry labels every editor control `automatic`, `guided`, or
`unavailable`. Resolution is fixed to accessibility role/name, Korean label,
documented shortcut, then a versioned DOM fallback. A duplicate or missing control
stops the operation. Checkpoints retain only the document hash, completed operation
IDs, verified draft URL, state, and diagnostic filenames, so resume does not duplicate
completed blocks or persist the article body.

Draft saving and final publication use different document-bound approval tokens.
Before publishing or scheduling, AutoSEO previews category, visibility, search,
comments, sympathy, CCL, sharing, tags, and time. An unclear result enters an
`unknown` state and cannot be automatically retried.

## Tistory editor and privacy boundary

`TistoryDocument v1` is independent of the browser and deterministically renders
structured blocks as Markdown or escaped HTML. Browser composition uses a dedicated
Tistory profile and selects one source mode for the complete body. Local export
therefore remains usable even when the live editor selector map needs maintenance.

Before account access, each static attachment receives a local face plan. Frontal
and profile detections are ranked by area and prominence. One main face is retained
only when unambiguous; other faces are mosaicked, and explicit face IDs or rectangular
regions override the default. Original files are never overwritten and metadata is
stripped from private derivatives by default.

Uploads run from an empty basic editor, accept exactly one new allowlisted Kakao or
Tistory CDN URL, and persist only that URL and its state. An interrupted or ambiguous
upload enters `unknown` so resume cannot duplicate it. The final Markdown/HTML buffer,
title, tags, and draft save use checked operation hashes. Publish and schedule remain
separate one-click, per-document approval boundaries.

## Maintainer rules

- Keep each skill independently understandable and scoped to one user intent.
- Put deep reference material beside the skill that consumes it.
- Prefer deterministic helpers for security-sensitive parsing and repeatable scoring.
- Add a focused regression test with every security or data-integrity fix.
- Keep network bounds, timeouts, output paths, and confidence labels explicit.
- Avoid new infrastructure until a real workflow requires it.
