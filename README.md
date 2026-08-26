# AutoSEO

AutoSEO is an open-source Codex plugin for search engine optimization (SEO) and
generative engine optimization (GEO). It packages focused workflows for website
audits, technical SEO, content quality, structured data, search experience,
local and international SEO, performance, and AI-search visibility.

## Status

AutoSEO 0.2.0 is a functional-parity public preview and a **Skills-only** plugin.
It maps all 32 user-facing capability groups in the 2.2.5 reference baseline,
including the complete 41-playbook research-to-growth workflow library and the
provider-specific command surfaces.

Host-level mechanics intentionally follow Codex: prompt invocation, skill discovery,
connector authorization, and plugin installation are not copied from another host.
Provider-backed measurements still require the respective authorized capability;
AutoSEO gives a documented fallback and never fabricates unavailable metrics.

The repository marketplace layout is ready for local development and GitHub-based
distribution. Store screenshots and formal listing review remain before marketplace
submission.

## Install from GitHub

```bash
codex plugin marketplace add HarrisonCho407/AutoSEO-codex --ref main
codex plugin add autoseo@autoseo
```

Restart the ChatGPT desktop app or start a new Codex session after installation.

## Example prompts

- `@autoseo Audit https://example.com for SEO and AI-search visibility.`
- `@autoseo Create a technical SEO remediation plan for this site.`
- `@autoseo Review this page's content, schema, and Core Web Vitals.`
- `@autoseo Build a topic cluster and internal-link plan for this keyword.`
- `@autoseo workflow optimize https://example.com`
- `@autoseo dataforseo serp "technical seo"` (when authorized)

## Safety model

- Website analysis is read-only by default.
- User-supplied URLs pass through SSRF and redirect validation before network access.
- Credentials are never committed and should be supplied through environment variables
  or user-owned configuration files.
- Indexing submissions and other external write actions require explicit confirmation.
- Runtime dependencies are installed only when the user explicitly requests setup.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) for details.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Command guide](docs/COMMANDS.md)
- [Feature coverage](docs/FEATURE_COVERAGE.md)
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
plugins/autoseo/scripts/autoseo setup
```

Setup creates an isolated environment outside the repository. It does not install
packages globally.

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

[MIT](LICENSE) © 2026 HarrisonCho407.
