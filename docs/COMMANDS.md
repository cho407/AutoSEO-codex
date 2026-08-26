# AutoSEO Command Guide

AutoSEO is prompt-driven. Start with `@autoseo`, then name the capability and the
outcome. Natural-language details can follow any example below. Codex routes the
request to the smallest matching skill.

## Core analysis and planning

| Capability | Example |
|---|---|
| Setup | `@autoseo setup` |
| Runtime check | `@autoseo doctor` |
| Full audit | `@autoseo audit https://example.com` |
| One-page review | `@autoseo page https://example.com/product` |
| Technical SEO | `@autoseo technical https://example.com` |
| Content review | `@autoseo content https://example.com/guide` |
| Content humanization | `@autoseo content humanize <file-or-text>` |
| Claim verification | `@autoseo content verify <file-or-text>` |
| Content brief | `@autoseo content-brief brief <topic>` |
| Content outline | `@autoseo content-brief outline <topic>` |
| GEO review | `@autoseo geo https://example.com` |
| Strategic plan | `@autoseo plan <business-context>` |

Industry-specific plan templates are directly routable:

```text
@autoseo plan saas <context>
@autoseo plan local <context>
@autoseo plan ecommerce <context>
@autoseo plan publisher <context>
@autoseo plan agency <context>
```

## Site, page, and search-experience commands

```text
@autoseo schema detect <url-or-file>
@autoseo schema validate <url-or-file>
@autoseo schema generate <page-type>
@autoseo images audit <url>
@autoseo images serp <query>
@autoseo images optimize <image-or-directory>
@autoseo sitemap analyze <url-or-file>
@autoseo sitemap generate <site-or-url-list>
@autoseo competitor-pages audit <url>
@autoseo competitor-pages generate <comparison>
@autoseo hreflang audit <site-or-files>
@autoseo hreflang generate <locale-map>
@autoseo programmatic audit <site-or-template>
@autoseo programmatic plan <dataset-and-market>
@autoseo local <business-or-site>
@autoseo maps audit <business>
@autoseo maps grid <business-and-area>
@autoseo maps gbp <business>
@autoseo maps reviews <business>
@autoseo maps competitors <business-and-area>
@autoseo maps nap <business>
@autoseo maps schema <business>
@autoseo backlinks audit <domain>
@autoseo backlinks gap <domain-and-competitors>
@autoseo backlinks toxic <domain>
@autoseo backlinks new <domain>
@autoseo backlinks verify <file-or-domain>
@autoseo backlinks setup
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

## Strategy workflow library

The workflow library contains 41 guided playbooks across five stages. `catalog`
lists individual playbooks; a stage command recommends and runs the best match.

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

Refreshing performs a network read and writes a catalog file. AutoSEO shows the
official source and destination and requests confirmation before proceeding. It
does not silently replace an existing catalog.

## Google services

These commands use public endpoints or an already-authorized Google property. Any
credential flow, metered request, indexing notification, or other external write
requires the applicable confirmation.

```text
@autoseo google setup
@autoseo google pagespeed <url>
@autoseo google crux <url>
@autoseo google crux-history <url>
@autoseo google gsc <property>
@autoseo google inspect <url>
@autoseo google inspect-batch <url-list>
@autoseo google sitemaps <property>
@autoseo google index <url>
@autoseo google index-batch <url-list>
@autoseo google ga4 <property>
@autoseo google ga4-pages <property>
@autoseo google youtube <query>
@autoseo google youtube-video <video-id>
@autoseo google nlp <text-or-file>
@autoseo google entities <text-or-file>
@autoseo google keywords <seed>
@autoseo google volume <keyword-list>
@autoseo google entity <name>
@autoseo google safety <text-or-url>
@autoseo google quotas
@autoseo google report <input>
```

## Image generation

```text
@autoseo image-gen og <description>
@autoseo image-gen hero <description>
@autoseo image-gen product <description>
@autoseo image-gen infographic <description>
@autoseo image-gen custom <description>
@autoseo image-gen batch <description> [N]
```

The batch default is 3 and the maximum is 6. Generated assets include a visual QA,
filename, alt text, delivery-format guidance, and relevant OG or schema metadata.

## Firecrawl

Use only when an authorized Firecrawl capability is available. Otherwise AutoSEO
uses its bounded public-page and sitemap helpers when they can meet the request.

```text
@autoseo firecrawl crawl <url>
@autoseo firecrawl map <url>
@autoseo firecrawl scrape <url>
@autoseo firecrawl search <query>
```

## DataForSEO

AutoSEO estimates endpoint usage before a paid batch and requires explicit cost
confirmation. Missing authorization produces a precise fallback or limitation,
never invented data.

```text
@autoseo dataforseo serp <query>
@autoseo dataforseo serp-images <query>
@autoseo dataforseo serp-youtube <query>
@autoseo dataforseo youtube <query-or-video>
@autoseo dataforseo keywords <seed>
@autoseo dataforseo volume <keyword-list>
@autoseo dataforseo difficulty <keyword-list>
@autoseo dataforseo intent <keyword-list>
@autoseo dataforseo trends <keyword-list>
@autoseo dataforseo backlinks <domain>
@autoseo dataforseo competitors <domain>
@autoseo dataforseo ranked <domain>
@autoseo dataforseo intersection <domains>
@autoseo dataforseo traffic <domain>
@autoseo dataforseo subdomains <domain>
@autoseo dataforseo top-searches <location>
@autoseo dataforseo onpage <url>
@autoseo dataforseo tech <domain>
@autoseo dataforseo whois <domain>
@autoseo dataforseo content <query-or-url>
@autoseo dataforseo listings <business>
@autoseo dataforseo ai-scrape <prompt>
@autoseo dataforseo ai-mentions <brand>
@autoseo dataforseo costs
```

## Ahrefs

```text
@autoseo ahrefs metrics <domain-or-url>
@autoseo ahrefs backlinks <domain-or-url>
@autoseo ahrefs organic <domain>
@autoseo ahrefs content <domain-or-topic>
```

These commands require an authorized Ahrefs connector or API. AutoSEO states the
unavailable fields and offers public-data alternatives when authorization is absent.

## Bing and IndexNow

```text
@autoseo bing links <site>
@autoseo bing compare <site>
@autoseo bing submit <url>
@autoseo bing submit-batch <url-list>
@autoseo bing verify-indexnow <site>
```

`submit` and `submit-batch` are external writes. AutoSEO previews the exact URLs and
requires confirmation immediately before submission.

## Profound

```text
@autoseo profound citations <brand-or-domain>
@autoseo profound prompts <brand-or-domain>
@autoseo profound competitors <brand-or-domain>
@autoseo profound alerts <brand-or-domain>
```

## SE Ranking

```text
@autoseo seranking ai-visibility <brand-or-domain>
@autoseo seranking serp <query>
@autoseo seranking backlinks <domain>
@autoseo seranking competitors <domain>
```

Profound and SE Ranking commands require their respective authorized capabilities.
AutoSEO distinguishes unavailable provider data from zero-valued measurements.

## Local runtime

Bundled deterministic checks run through the plugin-local launcher:

```text
<plugin-root>/scripts/autoseo doctor --json
<plugin-root>/scripts/autoseo setup [--skip-browser]
<plugin-root>/scripts/autoseo run <allowlisted-script.py> [arguments]
```

The runtime accepts only bundled allowlisted helpers, not arbitrary scripts, extension
paths, or shell commands. General audits remain read-only; external writes and paid
requests are never implied.
