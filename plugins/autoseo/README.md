# AutoSEO plugin bundle

This directory is the distributable AutoSEO Codex plugin. It contains only
Skills-only workflows, local helper scripts, references, and brand assets. It
does not include a hosted service, embedded credentials, or an MCP server.

Version 0.3.0 covers 32 user-facing capability groups and ships 41 guided
workflow playbooks. Every workflow has a no-subscription path through Codex-native
research, public web data, local analysis, or optional no-cost first-party data.
Commercial-only metrics and live monitoring outcomes are excluded instead of being
replaced with fabricated values. Host-specific invocation, authorization, and
installation follow Codex conventions.

Resolve this directory as `<plugin-root>` whenever a skill runs a bundled helper:

```text
<plugin-root>/scripts/autoseo doctor --json
<plugin-root>/scripts/autoseo run <script.py> [arguments]
```

Dependency setup is explicit:

```text
<plugin-root>/scripts/autoseo setup
```

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
