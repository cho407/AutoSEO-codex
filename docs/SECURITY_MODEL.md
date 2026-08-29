# Security Model

## Trust boundaries

| Boundary | Default | Additional requirement |
|---|---|---|
| Local repository reads | Allowed within the user's requested scope | Treat file content as untrusted data |
| Public website reads | Allowed for the requested target | URL validation, redirect checks, timeout, and bounded crawl |
| Local report creation | Allowed when it is the requested deliverable | User-selected location; preserve existing files |
| Separately billable data endpoint | Not shipped | Reject the workflow and explain the free-only boundary |
| Search-engine write | Blocked | Exact target preview and explicit approval |
| Publishing or website mutation | Blocked | Separate, explicit authorization and review |
| Naver draft write | Preview only | Exact document-bound approval, visible headed browser |
| Naver publish or schedule | Blocked | Fresh final-settings preview and per-post approval token |
| Package or connector installation | Blocked by default | Explicit setup/install request |

## Primary threats and controls

### Server-side request forgery

URL validation rejects non-HTTP schemes, user information in authorities, parser-confusing
backslashes or encoded authorities, localhost, metadata hosts, obfuscated numeric hosts,
and non-public IP ranges. Strict requests validate every DNS result and pin the approved
address. Redirects and rendered-page requests are checked independently.

### Prompt injection and untrusted page content

Fetched pages, robots files, metadata, structured data, connector output, and local input
files are evidence, never instructions. Skills ignore embedded requests to reveal secrets,
run commands, install software, expand scope, or contact another system.

### Command and supply-chain execution

Subprocesses receive argument arrays and do not invoke a shell. The runtime dispatches
only bundled allowlisted basenames. Optional Unlighthouse support resolves an already
trusted executable and never uses an automatic package downloader.

### Credentials and sensitive data

No publisher credential is bundled. Diagnostics redact common secret patterns and local
home paths. Optional first-party credentials stay in user-controlled environment variables
or credential stores. Reports should omit personal data unless it is necessary and explicitly
in scope.

### Resource exhaustion

Crawls, response bodies, subprocesses, routes, and API calls use documented bounds and
timeouts. Default site audits are intentionally smaller than their hard maximum. Public
research and batch inputs are capped and report the observed sample size.

### Stateful Naver browser automation

Naver uses a dedicated persistent browser profile with owner-only permissions.
AutoSEO never reads or exports cookies from that directory and never handles login,
two-factor authentication, or CAPTCHA. The top-level page must remain on allowlisted
Naver login or Blog hosts, while subresources still pass the public-network route
guard.

Editor controls are discovered through accessibility role/name, Korean label,
shortcut, and versioned DOM fallback in that order. Multiple matches stop the run.
Checkpoints contain only a source hash, completed operation IDs, verified draft URL,
publication state, and diagnostic filenames. A changed source hash cannot silently
resume an older operation set.

Draft write approval and final publication approval are separate and bound to the
exact normalized document. Publication is disabled in automated tests. Once a click
has an unclear result, the state becomes `unknown` and automatic retry is refused.
This reduces duplicate-post risk but cannot eliminate platform-side failure or UI
change risk; live-editor validation remains required for each release candidate.

## Residual risks

Browser engines resolve networking outside Python's socket-level DNS pinning, so rendered
workflows additionally rely on request interception and revalidation. Public and first-party
APIs can change behavior, availability, or quotas. Generated recommendations can be wrong or
stale. Users should review high-impact changes and validate current primary documentation
before publishing or submitting data.

Failure screenshots can contain visible draft or account information. They remain
local and are excluded from Git and release archives, but users must protect and
delete them when no longer needed.
