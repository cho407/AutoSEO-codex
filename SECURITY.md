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

## Supported versions

Security fixes target the latest published AutoSEO release and the `main` branch.
