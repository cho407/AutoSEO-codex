# Feature Coverage

AutoSEO 0.3.0 exposes 32 routable SEO/GEO capability groups and 41 guided
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
| `autoseo-geo` | AI-search access, entity, attribution, citation, and answer readiness |
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

The bundle includes helpers for SSRF-safe fetching, rendered-page capture, HTML
parsing, sitemap discovery, structured data, performance evidence, authorized
first-party reports, Common Crawl link discovery, direct backlink verification, local
snapshot comparison, RDAP, content checks, image metadata, and report generation.

Host-specific agent files, hooks, installers, and invocation syntax are structural
implementation details and are not copied. Their relevant user-facing outcomes are
represented through Codex skills, the allowlisted runtime, validation, and consent gates.
