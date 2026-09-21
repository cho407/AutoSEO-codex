# AutoSEO plugin bundle

This directory is the distributable AutoSEO Codex plugin. It contains skills,
local helpers, schemas, references, and brand assets, with no hosted service,
embedded credential, separately billable data integration, or MCP server.

Version 0.6.0-rc.1 covers 38 user-facing capability groups, five independent
SEO/AEO/GEO/LLMO/NEO readiness lanes, and 41 guided workflow playbooks. A shared
`EvidenceBundle v1` prevents repeated page collection across lanes. Commercial-only
metrics and live monitoring outcomes are excluded instead of being fabricated.

The natural Korean writing workflow keeps a confirmed identity and tone profile in
an owner-only local file, asks only missing planning questions on first use, and
performs a fact-preserving semantic polish plus conservative translationese checks.
`OptimizationReport v1` combines only scoreable lane readiness, while
`TrendEvidence v1` deduplicates and corroborates dated current-topic sources.

Presentation guidance is split into a universal `balanced-editorial` quality floor
and optional local profiles. The personal `tactile-howto` profile supports centered
short prose, tactile square covers, 4:5 procedure images, navy/coral callouts and
real source screenshots; it is not a ranking signal or a universal default. See
`skills/autoseo-writing/references/blog-style-standard.md`.

`TrendCollection v1` adds account-free public RSS collection, 14 local categories,
multi-category/keyword/exclusion filters and explicit local JSON export. Category
research uses bounded Codex web searches imported as `TrendResearch v1`; generated
queries alone are not completed research. News discovery does not imply measured
search demand, and the short RSS sample is not a complete category ranking.
Ask `@autoseo 여행과 IT 카테고리별 트렌드를 조사하고 수집해줘` or use
`@autoseo search-data trending KR --category 여행`. No additional browser, provider
login, subscription service or runtime dependency is needed beyond the existing lite runtime.

The PC Naver Blog SmartEditor ONE adapter can launch regular Chrome with a dedicated
visible profile or attach over loopback CDP to one already-open editor tab. Learned
frame/scope hints and catalog-owned selectors avoid repeated full-surface scans, and
the title-only command verifies that the article body stayed unchanged before one
draft save. Draft writes and every publish/schedule action have separate approval
boundaries. Candidate-based controls are guided, ambiguous UI stops safely, and an
unclear publication result is never retried. Live Naver and Tistory editor
verification is still required before promoting this release candidate to 0.6.0.

The Tistory adapter renders `TistoryDocument v1` to Markdown or HTML without a
browser, or composes it in a separate guarded visible profile. Static attachments
can be processed locally with a privacy-first bystander mosaic: one unambiguous main
face is kept, other detected faces are mosaicked, and explicit face/region overrides
remain available. Live Tistory selector validation is required before stable release.

Resolve this directory as `<plugin-root>` whenever a skill runs a bundled helper:

```text
<plugin-root>/scripts/autoseo doctor --json
<plugin-root>/scripts/autoseo run <allowlisted-script.py> [arguments]
```

Dependency setup is explicit:

```text
<plugin-root>/scripts/autoseo setup --profile standard
```

Use `--profile lite` for browser-free analysis. Google and PDF/Excel integrations
are separate opt-ins through `--with google`, `--with image`, and `--with report`.

AutoSEO is distributed under the MIT License in `LICENSE`.

The initial functional inventory was developed with reference to
[claude-seo by AgricIDaniel](https://github.com/AgricIDaniel/claude-seo),
release 2.2.5, licensed under MIT. Adapted portions retain this notice:

> Copyright (c) 2026 agricidaniel
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
> of the Software, and to permit persons to whom the Software is furnished to do
> so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.
