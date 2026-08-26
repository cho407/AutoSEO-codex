# Feature Coverage

AutoSEO 0.2.0 provides 33 routable skills covering all 32 user-facing capabilities
in the 2.2.5 functional baseline. `autoseo-performance` and `autoseo-visual` remain
dedicated skills while their outcomes also participate in the full audit.

Functional parity is measured at the user-outcome level. Prompt syntax, skill discovery,
agent profile representation, hooks, connector authorization, and installation use the
host's native structure. A proprietary provider command is supported when its authorized
capability is present; without it, AutoSEO reports the missing measurement and follows the
documented fallback rather than fabricating data.

The inventory is enforced by `data/feature-parity.json` and regression tests. A skill
is not considered supported unless its folder, command surface, helper dependencies,
safety boundary, documentation, and fallback behavior validate together.

## Core workflows

| Skill | Capability |
|---|---|
| `autoseo` | Intent routing, full-audit coordination, evidence and consent policy |
| `autoseo-audit` | Bounded multi-page SEO/GEO audit and prioritized roadmap |
| `autoseo-page` | Deep review of one page |
| `autoseo-technical` | Crawlability, indexation, rendering, headers, robots, and technical signals |
| `autoseo-performance` | PageSpeed, CrUX, LCP subparts, preload, and performance diagnosis |
| `autoseo-visual` | Mobile, desktop, above-the-fold, accessibility-tree, and visual review |
| `autoseo-content` | Quality, E-E-A-T, factual support, citability, and human-review checks |
| `autoseo-content-brief` | Search-focused content briefs and page-type templates |
| `autoseo-schema` | Structured-data detection, validation, and generation |
| `autoseo-sitemap` | Sitemap discovery, analysis, and safe generation guidance |
| `autoseo-images` | Existing image performance, accessibility, metadata, and AI-label audits |
| `autoseo-image-gen` | Host-native creation briefs and SEO-ready image assets |
| `autoseo-geo` | AI-search visibility, crawler access, entity, attribution, and citation readiness |
| `autoseo-plan` | SEO/GEO strategy, prioritization, roadmaps, and industry templates |
| `autoseo-workflow` | 41 playbooks across discovery, authority, optimization, conversion, and local stages |
| `autoseo-programmatic` | Template/data quality controls for generated page collections |
| `autoseo-competitor-pages` | Comparison and alternative-page planning |
| `autoseo-hreflang` | International targeting, locale mapping, and hreflang validation |
| `autoseo-local` | Website-side local search signals, GBP alignment, and local schema |
| `autoseo-maps` | Geo-grid, map-pack, location, and local competitor intelligence |
| `autoseo-google` | Search Console, PageSpeed, CrUX, GA4, YouTube, and Google API workflows |
| `autoseo-backlinks` | Link profile analysis, public-source discovery, and live verification |
| `autoseo-cluster` | SERP-overlap topic clusters, internal-link maps, briefs, and optional drafts |
| `autoseo-sxo` | Search intent, information scent, conversion friction, and search experience |
| `autoseo-drift` | Baselines, comparisons, history, and regression reports |
| `autoseo-ecommerce` | Product, merchant, marketplace, schema, feed, and commerce readiness |

## Conditional providers

| Skill | Capability and fallback |
|---|---|
| `autoseo-dataforseo` | Paid SERP/merchant data with preflight cost control; local/public fallback |
| `autoseo-ahrefs` | Authorized Ahrefs data; routes to backlink workflows when unavailable |
| `autoseo-firecrawl` | Authorized crawl connector; routes to bounded local rendering when unavailable |
| `autoseo-bing` | Bing Webmaster reads and consent-gated IndexNow submissions |
| `autoseo-profound` | Authorized AI-citation intelligence; qualitative GEO fallback |
| `autoseo-seranking` | Authorized AI-visibility data; qualitative GEO fallback |
| `autoseo-unlighthouse` | Trusted local multi-page Lighthouse binary; no automatic package download |

## Deterministic helper coverage

The bundle includes helpers for SSRF-safe fetching, rendered-page capture, HTML parsing,
sitemap discovery, structured-data generation and validation, PageSpeed and CrUX data,
Google account reports, backlink providers and verification, drift baselines, commerce
checks, image metadata, content checks, and report generation. Helpers complement Codex
reasoning; they do not turn estimates into verified measurements or bypass provider terms.

## Parity boundaries

| Included | Host-native equivalent |
|---|---|
| 32 user-facing SEO/GEO capability groups | Codex skill routing and `@autoseo` prompts |
| 41 guided workflow playbooks | Local validated catalog with select, recommend, export, and refresh operations |
| Provider-specific command outcomes | Authorized Codex connectors or tools plus explicit fallbacks |
| Audit decomposition and parallelizable specialist work | Focused skills selected or coordinated by the AutoSEO orchestrator |
| Schema and report validation | Deterministic allowlisted helpers and test gates |

Host-specific agent files, hooks, extension installers, and invocation syntax are
structural implementation details and are not copied. Their user-facing outcomes are
represented by the skills, runtime, validation, and consent gates above.
