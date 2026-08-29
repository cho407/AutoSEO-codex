# AutoSEO

AutoSEO is a free, open-source Codex plugin for SEO, AEO, GEO, LLMO, and NEO.
It collects each page once, reuses the same normalized evidence across independent
readiness lanes, and includes guarded PC Naver Blog SmartEditor ONE composition.

## Status

AutoSEO 0.4.0-rc.1 is a no-subscription release candidate and a **Skills-only**
plugin. It maps 36 user-facing capability groups and the complete 41-playbook
research-to-growth library. Every shipped workflow uses Codex-native research,
public web data, local analysis, or optional no-cost data from a property the user
owns. No paid dataset or subscription API is included.

The five lanes answer different questions:

| Lane | Measures |
|---|---|
| SEO | Discovery, crawling, indexing, presentation, and technical/content readiness |
| AEO | Direct-answer quality, intent coverage, and claim-to-source support |
| GEO | Generative-search crawler access and observed citation readiness |
| LLMO | Brand fact consistency and verifiable closed-book model knowledge |
| NEO | Korean/Naver discovery, intent, Search, and AI Briefing readiness |

Readiness scores never promise rankings, citations, or exposure. Outcome samples
remain separate, and unavailable evidence is marked `unmeasured`, not zero.

Host-level mechanics follow Codex: prompt invocation, skill discovery, authorization,
and plugin installation use Codex conventions. Outcomes that genuinely require a
commercial dataset are excluded instead of being represented by invented numbers.
This includes proprietary search-volume, traffic, authority and difficulty scores,
automated commercial AI-answer monitoring, and live geo-grid rank tracking.

The Naver editor is intentionally labeled release-candidate functionality until
the manual, user-owned-account checklist is completed against the live PC editor.
The default action is a confirmed draft save. Publish and schedule require a fresh,
document-specific approval and are never retried when the result is unclear.

## Install from GitHub

```bash
codex plugin marketplace add cho407/AutoSEO-codex --ref main
codex plugin add autoseo@autoseo
```

Restart the ChatGPT desktop app or start a new Codex session after installation.

## Example prompts

- `@autoseo Audit https://example.com for SEO and AI-search visibility.`
- `@autoseo audit all https://example.com`
- `@autoseo neo visibility "서울 성수동 카페"`
- `@autoseo naver-editor compose ./article.naver-document.json`
- `@autoseo Create a technical SEO remediation plan for this site.`
- `@autoseo Review this page's content, schema, and Core Web Vitals.`
- `@autoseo Build a topic cluster and internal-link plan for this keyword.`
- `@autoseo workflow optimize https://example.com`
- `@autoseo search-data serp "technical seo"`
- `@autoseo ai-citations citations example.com`

## Safety model

- Website analysis is read-only by default.
- User-supplied URLs pass through SSRF and redirect validation before network access.
- Credentials are never committed and should be supplied through environment variables
  or user-owned configuration files.
- Indexing submissions and other external write actions require explicit confirmation.
- Naver login, two-factor authentication, and CAPTCHA remain manual in a dedicated
  headed browser profile; cookies are never exported by AutoSEO.
- Naver publish and schedule actions require a new exact approval for every post.
- Runtime dependencies are installed only when the user explicitly requests setup.
- AutoSEO never routes a workflow to a separately billable data endpoint.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) for details.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Command guide](docs/COMMANDS.md)
- [Feature coverage](docs/FEATURE_COVERAGE.md)
- [Naver editor compatibility](plugins/autoseo/skills/autoseo-naver-editor/references/feature-compatibility.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security model](docs/SECURITY_MODEL.md)

## Repository layout

```text
.agents/plugins/marketplace.json   Repository marketplace
plugins/autoseo/                   Distributable plugin
  .codex-plugin/plugin.json        Plugin manifest
  skills/                          AutoSEO workflows
  scripts/                         Deterministic analysis helpers
  assets/                          Plugin brand assets
submission/                        Public-listing and review materials
tests/                             Validation and security regression tests
```

## Development

```bash
python3 -m pytest
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/autoseo
```

The managed analysis runtime is optional during repository validation:

```bash
plugins/autoseo/scripts/autoseo doctor --json
plugins/autoseo/scripts/autoseo setup --profile standard
```

Setup creates an isolated environment outside the repository. It does not install
packages globally. Use `--profile lite` for browser-free analysis and add
`--with google` or `--with report` only when those optional workflows are needed.

Run the reproducible collection benchmark with:

```bash
plugins/autoseo/scripts/autoseo run benchmark_evidence.py
```

The benchmark uses a local 20-page fixture to measure architecture overhead. It is
not a prediction of internet, browser, ranking, or traffic performance.

## Acknowledgement

The initial feature inventory and workflow coverage were developed with reference
to [claude-seo by AgricIDaniel](https://github.com/AgricIDaniel/claude-seo),
with functional coverage checked against release 2.2.5.
That project is distributed under the MIT License. Portions adapted from that
work retain the following notice:

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

## License

[MIT](LICENSE) © 2026 cho407.
