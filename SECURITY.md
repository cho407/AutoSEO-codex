# Security Policy

## Reporting a vulnerability

Please use GitHub's private security advisory flow for this repository. Do not
include live API keys, access tokens, customer data, or exploit payloads in a
public issue.

Include the affected version, the smallest reproducible example, likely impact,
and any suggested remediation. Maintainers will acknowledge a valid report and
coordinate disclosure after a fix is available.

## Security boundaries

AutoSEO is a local, Skills-only plugin. It can:

- read public web pages after URL validation;
- read user-selected local files;
- create local reports and analysis artifacts;
- call public or no-cost first-party APIs only when the user has configured any
  required property access; and
- perform an external write such as IndexNow submission only after explicit consent.
- compose a draft in a visible, user-owned Naver Blog editor after a scoped draft
  approval, and publish or schedule only after a separate per-post approval.
- export Tistory Markdown/HTML locally, compose a user-owned Tistory draft in a
  separate visible profile, and publish or schedule only after per-post approval.
- create a new local privacy derivative that mosaics selected detected faces or
  explicit regions without overwriting the original.

AutoSEO does not operate a hosted backend, collect telemetry, require a shared
publisher credential, or ship a separately billable data integration.

## Defensive controls

- HTTP and HTTPS are the only accepted URL schemes.
- Loopback, private, reserved, link-local, multicast, and metadata endpoints are blocked.
- Redirects and rendered-page subresources are revalidated.
- Network calls use TLS verification, bounded timeouts, and size limits where supported.
- Subprocesses use argument arrays rather than a shell.
- The managed runtime executes only allowlisted bundled scripts.
- Credential output and common secret patterns are redacted.
- OAuth token files are written with owner-only permissions where supported.
- Naver editor profiles use a dedicated owner-only directory. AutoSEO does not
  export, print, or copy browser cookies outside it.
- Naver checkpoints contain hashes and operation IDs rather than article text;
  missing or ambiguous controls stop instead of triggering a guessed click.
- Automated test environments block Naver publish and schedule actions before any
  editor setting or publish control is touched.
- An unclear publication result is recorded as unknown and is never retried
  automatically, preventing duplicate posts.
- Tistory checkpoints track one-attempt media upload states and allowlisted hosted
  URLs; an unclear upload is never retried automatically.
- Face processing is local and optional. Originals are immutable, output paths reject
  symlinks, and derived files strip metadata by default.

## Naver editor artifacts

The visible editor can show private drafts, account names, and personal library
items. A failure screenshot can therefore be sensitive even though it stays local.
Profiles, checkpoints, compatibility maps, and diagnostics are excluded from Git
and release archives. Users should review and delete diagnostics after resolving a
failure. AutoSEO does not support bulk publishing, login bypass, automatic comments,
sympathy, or neighbor actions.

## Tistory and privacy-image artifacts

Tistory uses a different dedicated profile and host allowlist. Login, two-factor
authentication, and CAPTCHA remain manual. Source-mode insertion happens once after
each image upload yields exactly one newly observed allowlisted Kakao/Tistory CDN URL.
Checkpoints can contain those URLs but not the title, body, cookies, or original path.

Automatic face detection can miss profiles, occlusions, reflections, or very small
people. The tool therefore exposes numbered faces and explicit regions, flags an
ambiguous main person, and does not claim privacy completeness from a zero-face result.
Users must review sensitive images before publication. Browser profiles, checkpoints,
diagnostics, and privacy derivatives are excluded from Git and release archives.

## Supported versions

Security fixes target the latest published AutoSEO release and the `main` branch.
