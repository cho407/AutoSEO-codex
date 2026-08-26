# AutoSEO 0.2.0

Functional-parity public preview of the AutoSEO Codex plugin.

## Added

- Complete 32-capability user-facing command inventory for the 2.2.5 baseline
- Forty-one original AutoSEO workflow playbooks across five operating stages
- Deterministic workflow catalog validation, discovery, recommendation, export,
  and consent-gated refresh
- Complete Ahrefs, Bing, DataForSEO, Firecrawl, image-generation, Profound,
  SE Ranking, and workflow subcommand surfaces
- A full command guide and machine-readable parity manifest
- Regression tests for capability coverage, command routing, release contents,
  refresh source allowlisting, network consent, and overwrite protection

## Safety defaults

- Read-only analysis by default
- No bundled credentials, hosted backend, or telemetry
- No automatic connector or external crawler download
- Consent required for paid calls, network refreshes, indexing submissions, and
  other external writes
- Bounded network responses, exact official-source allowlisting, safe output paths,
  and explicit overwrite controls
- SHA-pinned official CI actions and a deterministic release archive

## Compatibility

Prompt invocation, skill discovery, connector authorization, hooks, and installation
follow Codex conventions. Provider-specific live metrics require the corresponding
authorized capability; transparent local or public-data fallbacks remain available.
