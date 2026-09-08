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
@autoseo naver-editor learn
@autoseo naver-editor compose <topic-or-document>
@autoseo naver-editor resume <draft>
@autoseo naver-editor verify-draft <document>
@autoseo naver-editor publish <draft>
@autoseo naver-editor schedule <draft-and-time>
@autoseo tistory-editor doctor
@autoseo tistory-editor learn
@autoseo tistory-editor export-markdown <document>
@autoseo tistory-editor export-html <document>
@autoseo tistory-editor compose <topic-or-document>
@autoseo tistory-editor resume <draft>
@autoseo tistory-editor verify-draft <document>
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

The Naver editor commands use a dedicated visible Chromium profile under
`AUTOSEO_DATA_DIR`. Login, two-factor authentication, and CAPTCHA remain manual.
Compose and resume first show the exact draft scope and require confirmation
before editing or saving. Publish and schedule show all final settings and require
a new document-specific approval token for every post. An unclear result is never
retried automatically.

Tistory export commands are local and require no login. Compose uses one Markdown
or HTML source-buffer write in a separate visible profile. Attached static images
default to local bystander mosaicing: a clear main face is kept, other detected
faces are mosaicked, and ambiguous group photos mosaic all detected faces for
review. Upload and publication each use one-attempt, approval-bound state; unclear
results are not retried.

For either editor, close the reviewed saved session and request `verify-draft` to
reopen the identified draft without writing. A fresh save notification is not a
readback receipt. `verified` requires matching content in a different browser
session; missing identity or incompatible mode/fingerprint is unavailable, and
changed content is a mismatch. Publication requires verified readback and the usual
per-post approval. No real-account success is implied by local browser tests.

See the [current roadmap](ROADMAP.md) for remaining editor work and the proposed
search/feed/balanced title candidates; title candidate generation is not yet shipped.

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
@autoseo search-data onpage <url>
@autoseo search-data tech <domain>
@autoseo search-data rdap <domain>
@autoseo search-data content <query-or-url>
@autoseo search-data listings <business>
@autoseo search-data ai-results <prompt>
@autoseo search-data ai-mentions <brand>
@autoseo search-data methods
```

For current or trending content, the default research window is 24 hours for a
breaking topic and 7 days for sustained interest. AutoSEO can use Google Trends
Trending Now RSS/export as one relative signal, but it requires an independent
dated source before calling a topic confirmed. Duplicate URLs are removed and the
result exposes freshness, relevance, corroboration, relative velocity, and refresh time.

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
