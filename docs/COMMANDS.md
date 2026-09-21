# AutoSEO Command Guide

AutoSEO is prompt-driven. Start with `@autoseo`, name the capability and outcome,
then add natural-language context. Every command below has a no-subscription path.
Sources and limitations are included in the result.

## Core analysis and planning

```text
@autoseo setup
@autoseo doctor
@autoseo audit https://example.com
@autoseo audit all https://example.com
@autoseo page https://example.com/product
@autoseo technical https://example.com
@autoseo content https://example.com/guide
@autoseo content humanize <file-or-text>
@autoseo content verify <file-or-text>
@autoseo content-brief brief <topic>
@autoseo content-brief outline <topic>
@autoseo writing draft <topic-or-brief>
@autoseo writing polish <draft>
@autoseo writing tone <preset>
@autoseo writing identity
@autoseo writing style
@autoseo writing score <draft-or-url>
@autoseo aeo audit <target>
@autoseo aeo brief <target>
@autoseo geo audit <target>
@autoseo geo citations <target>
@autoseo llmo audit <brand>
@autoseo llmo facts <brand>
@autoseo neo audit <target>
@autoseo neo visibility <target>
@autoseo neo brief <target>
@autoseo naver-editor doctor
@autoseo naver-editor plan <document>
@autoseo naver-editor capabilities
@autoseo naver-editor learn
@autoseo naver-editor compose <topic-or-document>
@autoseo naver-editor resume <draft>
@autoseo naver-editor revise-title
@autoseo naver-editor publish <draft>
@autoseo naver-editor schedule <draft-and-time>
@autoseo tistory-editor doctor
@autoseo tistory-editor plan <document>
@autoseo tistory-editor capabilities
@autoseo tistory-editor learn
@autoseo tistory-editor export-markdown <document>
@autoseo tistory-editor export-html <document>
@autoseo tistory-editor compose <topic-or-document>
@autoseo tistory-editor resume <draft>
@autoseo tistory-editor publish <draft>
@autoseo tistory-editor schedule <draft-and-time>
@autoseo plan <business-context>
@autoseo plan saas <context>
@autoseo plan local <context>
@autoseo plan ecommerce <context>
@autoseo plan publisher <context>
@autoseo plan agency <context>
```

Writing commands are optional shortcuts. Natural requests such as “이 주제로
네이버 글 써줘”, “번역투 없이 다듬어줘”, or “전문가의 쉬운 말투로 바꿔줘”
enter the same flow. On first use AutoSEO reuses known context, asks only the
missing writer basis, audience, reader outcome, and tone questions, then offers a
local profile for confirmation. A one-off tone change is not saved automatically.

For a draft, `writing score` reports measured style diagnostics, not factual or semantic quality. For a URL, it runs
the selected readiness lanes and combines them as `OptimizationReport v1` only when
every selected lane is independently scoreable; the report always shows evidence
coverage and never predicts rank or traffic.

Presentation profiles are local and optional. `balanced-editorial` is the universal
fallback. After reviewing the profile, an author may select the personal
`tactile-howto` direction with `blog_style.py set tactile-howto --confirm`; it
guides centered short prose, square/4:5 image ratios, tactile paper, navy/coral
accents and real screenshot callouts. It is not a ranking signal or a promise of
views. See [the blog presentation standard](BLOG_STYLE_STANDARD.md).

The Naver editor commands use a dedicated visible Chromium profile under
`AUTOSEO_DATA_DIR`. Login, two-factor authentication, and CAPTCHA remain manual.
An explicit compose or resume request shows a compact draft scope, then edits and
saves once after login without a second save confirmation. Publish and schedule show
all final settings and require a new document-specific approval token for every post.
An unclear result is never retried automatically.

Tistory export commands are local and require no login. Compose uses one Markdown
or HTML source-buffer write in a separate visible profile. Attached static images
default to local bystander mosaicing: a clear main face is kept, other detected
faces are mosaicked, and ambiguous group photos mosaic all detected faces for
review. Upload and publication each use one-attempt, approval-bound state; unclear
results are not retried.

For either editor, compose and resume record a fresh save acknowledgement and the
source/surface fingerprints in the active editor session. The workflow does not
close and reopen a session to test persistence. An interrupted save stops for
manual reconciliation and is never retried automatically. Publication still checks
the exact draft identity and current fingerprint, then requires the usual
per-post approval. No real-account success is implied by local browser tests.

New Korean blog articles contain at least 1,500 body characters excluding whitespace,
with a representative hero image and an explanatory diagram or visual summary.
Supporting images are added where useful. A requested topic is researched directly;
without one, recent blog topics/categories are sampled once before selecting the
strongest corroborated current trend in that subject (or across subjects when no
pattern is observable). Only aggregate author context is retained. The chosen category
is stored in the document; current drivers apply it in the final publication dialog.
English editor labels are ranked from page metadata while Korean text stays unchanged.
Routine writing loads only the relevant guide and skips release tests/repeated diagnostics.

See the [current roadmap](ROADMAP.md) for remaining editor work and the proposed
search/feed/balanced title-candidate command; the no-topic trend routing above is
already part of blog mode.

## Site and page workflows

```text
@autoseo schema detect <url-or-file>
@autoseo schema validate <url-or-file>
@autoseo schema generate <page-type>
@autoseo images audit <url>
@autoseo images serp <query>
@autoseo images optimize <image-or-directory>
@autoseo images mosaic <image>
@autoseo sitemap analyze <url-or-file>
@autoseo sitemap generate <site-or-url-list>
@autoseo competitor-pages audit <url>
@autoseo competitor-pages generate <comparison>
@autoseo hreflang audit <site-or-files>
@autoseo hreflang generate <locale-map>
@autoseo programmatic audit <site-or-template>
@autoseo programmatic plan <dataset-and-market>
@autoseo local <business-or-site>
@autoseo cluster plan <topic>
@autoseo cluster execute <approved-plan>
@autoseo cluster map <plan-or-site>
@autoseo sxo audit <url>
@autoseo sxo wireframe <page-intent>
@autoseo sxo personas <market>
@autoseo drift baseline <url-or-site>
@autoseo drift compare <url-or-site>
@autoseo drift history <url-or-site>
@autoseo ecommerce audit <site>
@autoseo ecommerce products <site-or-feed>
@autoseo ecommerce gaps <site-and-competitors>
@autoseo ecommerce schema <product-or-site>
@autoseo unlighthouse audit <url>
```

## Public crawl and discovery

These commands use Codex web research, direct public-page reads, sitemaps, robots
files, and bounded local rendering.

```text
@autoseo crawl crawl <url>
@autoseo crawl map <url>
@autoseo crawl scrape <url>
@autoseo crawl search <query>
```

## Search evidence

Search evidence is a dated, bounded sample. Relative demand and competition signals
are transparent proxies; they are not exact search volume, traffic, rank, or difficulty.

```text
@autoseo search-data serp <query>
@autoseo search-data serp-images <query>
@autoseo search-data serp-youtube <query>
@autoseo search-data youtube <query-or-video>
@autoseo search-data keywords <seed>
@autoseo search-data demand <keyword-list>
@autoseo search-data difficulty <keyword-list>
@autoseo search-data intent <keyword-list>
@autoseo search-data trends <keyword-list>
@autoseo search-data backlinks <domain>
@autoseo search-data competitors <domain>
@autoseo search-data ranked <domain>
@autoseo search-data intersection <domains>
@autoseo search-data traffic <domain>
@autoseo search-data subdomains <domain>
@autoseo search-data trending <location>
@autoseo search-data trending KR --category 여행 --category IT
@autoseo search-data trending KR --keyword 캠핑 --exclude 사고 --window 7d
@autoseo search-data categories
@autoseo search-data onpage <url>
@autoseo search-data tech <domain>
@autoseo search-data rdap <domain>
@autoseo search-data content <query-or-url>
@autoseo search-data listings <business>
@autoseo search-data ai-results <prompt>
@autoseo search-data ai-mentions <brand>
@autoseo search-data methods
```

Overall collection fetches the public Google Trends RSS once and groups its sample
into local categories. Category requests also execute bounded Codex-native web
research for the selected subject; no extra provider login/API key is needed.
The default window is 24 hours; use 7 days for sustained topics. A wider window
does not backfill feed history. Repeated category/keyword filters use OR, exclusions
win, and an empty category is never replaced by unrelated headlines.

The 14 categories cover IT/technology/appliances, economy/business, travel, food,
beauty/fashion, parenting/education, health/exercise, lifestyle/shopping,
entertainment, sports, culture/games, politics, society/local and world. These are
AutoSEO editorial categories, not official provider categories. Unrecognized custom
subjects can use `--keyword`; `categories` lists IDs and Korean aliases.
Headline-only matches are review hints, not category assignments; an unrelated
celebrity keyword does not become a travel topic just because its news mentions travel.

For direct helper usage:

```text
<plugin-root>/scripts/autoseo run trend_collect.py categories
<plugin-root>/scripts/autoseo run trend_collect.py plan --category 여행
<plugin-root>/scripts/autoseo run trend_collect.py collect --market KR
<plugin-root>/scripts/autoseo run trend_collect.py collect --category 여행 --research-input <research.json> --output <collection.json>
```

`plan` only creates query suggestions. The skill executes them with native web
tools and records inspected URLs/dates under `TrendResearch v1`; `collect` imports
those observations and returns `TrendCollection v1`. Output defaults to stdout,
and existing output files require `--overwrite`. `--rss-file` replaces live HTTP
with a supplied snapshot, and `--as-of` is for explicit historical evaluation.

Results distinguish a Google-observed search surge from a dated topic with
unmeasured demand. Feed traffic buckets stay buckets, exact volume stays null,
and sorting by newest evidence is not a search/popularity ranking. The collector
does not claim complete coverage, Naver realtime ranks or immediate updates.
Before drafting, corroborate original facts with independent dated sources using
the existing per-topic `trend_evidence.py` workflow. Relative interest is not growth
velocity. Collection alone does not create articles, schedules or publications.

## Authority and backlinks

```text
@autoseo authority metrics <domain-or-url>
@autoseo authority backlinks <domain-or-url>
@autoseo authority organic <domain>
@autoseo authority content <domain-or-topic>
@autoseo backlinks audit <domain>
@autoseo backlinks gap <domain-and-competitors>
@autoseo backlinks toxic <domain>
@autoseo backlinks new <domain>
@autoseo backlinks verify <file-or-domain>
@autoseo backlinks setup
```

Authority results use observable evidence such as referring-domain diversity,
verified links, indexed content, first-party performance, and cited assets. AutoSEO
does not emit a proprietary authority score.

## AI-search evidence

```text
@autoseo ai-citations citations <brand-or-domain>
@autoseo ai-citations prompts <brand-or-domain>
@autoseo ai-citations competitors <brand-or-domain>
@autoseo ai-citations alerts <brand-or-domain>
@autoseo ai-visibility overview <brand-or-domain>
@autoseo ai-visibility serp <query>
@autoseo ai-visibility backlinks <domain>
@autoseo ai-visibility competitors <domain>
```

The commands sample answer surfaces available in the active Codex environment and
can compare saved local observations. They do not claim exhaustive cross-model tracking.

## Maps and local evidence

```text
@autoseo maps audit <business>
@autoseo maps gbp <business>
@autoseo maps reviews <business>
@autoseo maps competitors <business-and-area>
@autoseo maps nap <business>
@autoseo maps schema <business>
```

Public OpenStreetMap geocoding is used only for small, policy-compliant lookups.
Systematic live geo-grid rank tracking is not included.

## Google first-party and public data

```text
@autoseo google setup
@autoseo google pagespeed <url>
@autoseo google crux <url>
@autoseo google crux-history <url>
@autoseo google gsc <property>
@autoseo google inspect <url>
@autoseo google inspect-batch <url-list>
@autoseo google sitemaps <property>
@autoseo google index <eligible-url>
@autoseo google index-batch <eligible-url-list>
@autoseo google ga4 <property>
@autoseo google ga4-pages <property>
@autoseo google youtube <query>
@autoseo google youtube-video <video-id>
@autoseo google quotas
@autoseo google report <input>
```

Some commands require a no-cost cloud key, service account, or verified property.
The Indexing API commands are restricted to eligible `JobPosting` and
`BroadcastEvent` pages and require confirmation immediately before submission.

## Bing and IndexNow

```text
@autoseo bing links <site>
@autoseo bing compare <site>
@autoseo bing submit <url>
@autoseo bing submit-batch <url-list>
@autoseo bing verify-indexnow <site>
```

`submit` and `submit-batch` preview the exact URLs and require confirmation immediately
before the external write.

## Strategy workflow library

```text
@autoseo workflow overview
@autoseo workflow find <business-context>
@autoseo workflow leverage <business-context>
@autoseo workflow optimize <site-or-problem>
@autoseo workflow win <market-or-goal>
@autoseo workflow local <business-and-area>
@autoseo workflow catalog [stage]
@autoseo workflow refresh
```

The library contains 41 guided playbooks. Refresh shows its official source and
destination and requests confirmation before a network read and local write.

## Blog formatting

New blog writing also applies a consistent layout; see
[format presets](../plugins/autoseo/skills/autoseo-writing/references/blog-format.md).
`blog-centered` is the new-draft default; `article-readable` uses left-aligned prose
and `none` disables automatic styling. Existing documents are not migrated.

```text
<plugin-root>/scripts/autoseo run blog_format.py presets
<plugin-root>/scripts/autoseo run blog_format.py apply naver <document.json> --output <new-document.json>
<plugin-root>/scripts/autoseo run blog_format.py apply tistory <document.json> --preset article-readable --output <new-document.json>
```

Styled Tistory documents require `format: auto` or `html`; explicit Markdown is not
silently restyled or stripped. This local helper does not publish.

## Image generation

```text
@autoseo image-gen og <description>
@autoseo image-gen hero <description>
@autoseo image-gen product <description>
@autoseo image-gen infographic <description>
@autoseo image-gen custom <description>
@autoseo image-gen batch <description> [N]
```

These commands use only an image capability already included in the active Codex
environment. When it is unavailable without an additional purchase, AutoSEO returns
a production-ready creative brief instead.

## Local runtime

```text
<plugin-root>/scripts/autoseo doctor --json
<plugin-root>/scripts/autoseo setup [--profile standard|lite] [--with google] [--with image] [--with report]
<plugin-root>/scripts/autoseo run <allowlisted-script.py> [arguments]
```

The runtime accepts only bundled allowlisted helpers. It does not accept arbitrary
scripts, extension paths, or shell commands.
