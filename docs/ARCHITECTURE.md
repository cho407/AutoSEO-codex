# AutoSEO Architecture

AutoSEO is a Skills-only Codex plugin. Codex selects a focused skill, the skill
collects only the evidence needed for the request, and deterministic Python helpers
perform bounded parsing, validation, comparison, or report generation.

## Components

| Layer | Responsibility | Location |
|---|---|---|
| Plugin metadata | Identity, listing metadata, assets, skill discovery | `plugins/autoseo/.codex-plugin/` |
| Orchestration | Intent routing, audit policy, evidence and consent rules | `plugins/autoseo/skills/autoseo/` |
| Focused skills | Technical, content, GEO, local, commerce, and integration workflows | `plugins/autoseo/skills/` |
| Runtime boundary | Explicit setup, isolated environment, script allowlist | `plugins/autoseo/scripts/runtime.py` |
| Deterministic helpers | URL safety, crawling, parsing, API clients, scoring, exports | `plugins/autoseo/scripts/` |
| Static knowledge | Schemas, templates, update records, and skill references | `plugins/autoseo/schema/`, `data/`, and skill-local folders |

## Request flow

1. Codex routes the request to the narrowest matching AutoSEO skill.
2. The skill classifies the action as local read, public network read, local write,
   paid API call, or external write.
3. Public URLs are normalized and checked before any request. Redirects and rendered
   subresources are checked again.
4. A helper runs only through the runtime allowlist. The runtime never accepts an
   arbitrary path or shell command.
5. Findings include evidence, severity, impact, recommendation, and confidence.
6. Local files are written only when the requested workflow needs an artifact.
   Existing files and external systems are not changed without explicit approval.

## Runtime lifecycle

The repository itself has no import-time installer. `autoseo doctor` is read-only.
Only an explicit `autoseo setup` creates an isolated Python environment in a dedicated
AutoSEO data directory and installs the reviewed dependency set. Browser support is
optional and can be skipped.

Bundled helpers are addressed by basename and must appear in `ALLOWED_CORE_SCRIPTS`.
Path separators, traversal segments, unknown scripts, extension loaders, and the
runtime module itself are rejected.

## Extension model

Optional providers are represented as conditional skills, not bundled credentials or
auto-installers. A provider skill runs only when its connector is already available and
authorized. Paid calls require a cost estimate and consent. When a provider is absent,
AutoSEO returns a transparent local or public-data fallback instead of silently changing
the environment.

## Maintainer rules

- Keep each skill independently understandable and scoped to one user intent.
- Put deep reference material beside the skill that consumes it.
- Prefer deterministic helpers for security-sensitive parsing and repeatable scoring.
- Add a focused regression test with every security or data-integrity fix.
- Keep network bounds, timeouts, output paths, and confidence labels explicit.
- Avoid new infrastructure until a real workflow requires it.
