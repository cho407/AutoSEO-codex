# Feature Coverage

AutoSEO 0.4.0-rc.1 exposes 36 routable capability groups and 41 guided
research-to-growth playbooks. Every shipped workflow has a no-subscription path.
The inventory is enforced by `data/feature-parity.json`, the evidence-source policy
in `data/free-sources.json`, and regression tests.

Functional coverage is measured at the user-outcome level. Prompt syntax, skill
discovery, authorization, and installation use Codex-native structures. A workflow is
not considered supported unless its skill, command surface, helper dependencies,
safety boundary, documentation, and fallback behavior validate together.

## Core workflows

| Skill | Capability |
|---|---|
| `autoseo` | Intent routing, full-audit coordination, evidence policy, and consent boundaries |
| `autoseo-audit` | Bounded multi-page audit and prioritized roadmap |
| `autoseo-page` | Deep review of one page |
| `autoseo-technical` | Crawlability, indexation, rendering, headers, robots, and technical signals |
| `autoseo-performance` | PageSpeed, CrUX, LCP subparts, preload, and performance diagnosis |
| `autoseo-visual` | Mobile, desktop, above-the-fold, accessibility-tree, and visual review |
| `autoseo-content` | Quality, E-E-A-T, factual support, citability, and human-review checks |
| `autoseo-content-brief` | Search-focused briefs and page-type templates |
| `autoseo-schema` | Structured-data detection, validation, and generation |
| `autoseo-sitemap` | Sitemap discovery, analysis, and safe generation guidance |
| `autoseo-images` | Image performance, accessibility, metadata, and AI-label audits |
| `autoseo-image-gen` | Host-native creation briefs and SEO-ready image assets |
| `autoseo-aeo` | Question intent, direct answers, claim/source support, and answer readiness |
| `autoseo-geo` | Generative-search access, attribution, citation readiness, and observed sources |
| `autoseo-llmo` | Brand fact ledger, entity consistency, external corroboration, and closed-book limits |
| `autoseo-neo` | Korean intent, Yeti, Naver Search, and AI Briefing readiness and observations |
| `autoseo-naver-editor` | Guarded PC SmartEditor ONE draft composition, resume, publication, and scheduling |
| `autoseo-plan` | SEO/GEO strategy, prioritization, roadmaps, and industry templates |
| `autoseo-workflow` | 41 playbooks across discovery, authority, optimization, conversion, and local stages |
| `autoseo-programmatic` | Template and data-quality controls for generated page collections |
| `autoseo-competitor-pages` | Comparison and alternative-page planning |
| `autoseo-hreflang` | International targeting and locale validation |
| `autoseo-local` | Website-side local signals, business-profile alignment, and local schema |
| `autoseo-maps` | Public map, review, listing, NAP, and local competitor evidence |
| `autoseo-cluster` | SERP-overlap clusters, internal-link maps, briefs, and optional drafts |
| `autoseo-sxo` | Search intent, information scent, conversion friction, and search experience |
| `autoseo-drift` | Baselines, comparisons, history, and regression reports |
| `autoseo-ecommerce` | Product, category, assortment-gap, feed, and commerce-schema readiness |

## No-subscription evidence workflows

| Skill | Capability and method |
|---|---|
| `autoseo-crawl` | Direct public pages, robots, sitemaps, Codex web research, and bounded rendering |
| `autoseo-search-data` | Dated SERP samples, intent, relative signals, Common Crawl, RDAP, and first-party rows |
| `autoseo-authority` | Observable link, content, citation, and optional first-party performance evidence |
| `autoseo-backlinks` | Common Crawl discovery, current web research, direct verification, and local snapshots |
| `autoseo-ai-citations` | Observable citations and prompts with repeatable local snapshots |
| `autoseo-ai-visibility` | Combined public search, answer, backlink, and competitor evidence |
| `autoseo-google` | PageSpeed, CrUX, Search Console, GA4, YouTube, and eligible indexing workflows |
| `autoseo-bing` | Optional site-owner link reads and consent-gated IndexNow submissions |
| `autoseo-unlighthouse` | Trusted local multi-page Lighthouse binary; no automatic package download |

## Five readiness lanes

| Lane | Readiness scope | Outcome evidence kept separate |
|---|---|---|
| SEO | Discovery, crawling, indexing, canonicalization, structure, performance, and content | Search impressions, clicks, and positions |
| AEO | Question intent, direct answers, original contribution, and claim/source linkage | Snippet or answer-surface selection |
| GEO | Search-crawler access and citation-ready source structure | Dated prompt samples and cited competitor URLs |
| LLMO | Brand fact consistency and independent corroboration | Verifiably closed-book model answers; otherwise unmeasured |
| NEO | Korean intent, Yeti, feeds, Naver Search, and AI Briefing source readiness | Dated Naver result and AI Briefing samples |

Every lane uses `critical=4`, `high=3`, `medium=2`, and `low=1` weights. A score is
shown only after required eligibility is measured and at least 70% of applicable
evidence is present. Rankings, citations, model training, and Naver exposure are
never guaranteed.

## Naver editor compatibility

The first target is the PC Naver Blog SmartEditor ONE. Cafe, Place, Smart Store,
bulk publishing, automatic comments/sympathy/neighbors, and login bypass are out of
scope. The machine-readable source is `data/naver-editor-features.json`; the complete
human-readable status and live validation checklist are in the distributable
[feature compatibility reference](../plugins/autoseo/skills/autoseo-naver-editor/references/feature-compatibility.md).

## Deliberate exclusions

These outcomes do not have a trustworthy no-subscription equivalent and are not
shipped:

- exact proprietary search-volume, traffic, rank, difficulty, and authority metrics;
- exhaustive backlink indexes represented as complete;
- automated commercial AI-answer monitoring across third-party models;
- reliable live geo-grid rank tracking that needs a commercial service or
  user-operated infrastructure.

AutoSEO can provide bounded public samples and explicitly named relative proxies. It
always includes the method, date, sample size, confidence, and missing evidence, and
never relabels a proxy as a proprietary measurement.

## Deterministic helpers

The bundle includes helpers for SSRF-safe fetching, a shared `EvidenceBundle v1`,
single-browser rendered-page capture, five independent lane reports, Korean text and
Naver evidence, guarded SmartEditor automation, HTML parsing, sitemap discovery,
structured data, performance evidence, authorized
first-party reports, Common Crawl link discovery, direct backlink verification, local
snapshot comparison, RDAP, content checks, image metadata, and report generation.

Host-specific agent files, hooks, installers, and invocation syntax are structural
implementation details and are not copied. Their relevant user-facing outcomes are
represented through Codex skills, the allowlisted runtime, validation, and consent gates.
