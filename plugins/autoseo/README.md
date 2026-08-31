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

The PC Naver Blog SmartEditor ONE adapter uses a dedicated visible Playwright
profile. Draft writes and every publish/schedule action have separate approval
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
