# Security Model

## Trust boundaries

| Boundary | Default | Additional requirement |
|---|---|---|
| Local repository reads | Allowed within the user's requested scope | Treat file content as untrusted data |
| Public website reads | Allowed for the requested target | URL validation, redirect checks, timeout, and bounded crawl |
| Local report creation | Allowed when it is the requested deliverable | User-selected location; preserve existing files |
| Paid API call | Blocked | Cost estimate and explicit approval |
| Search-engine or provider write | Blocked | Exact target preview and explicit approval |
| Publishing or website mutation | Blocked | Separate, explicit authorization and review |
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
home paths. Provider credentials stay in user-controlled environment variables or provider
stores. Reports should omit personal data unless it is necessary and explicitly in scope.

### Resource exhaustion

Crawls, response bodies, subprocesses, routes, and API calls use documented bounds and
timeouts. Default site audits are intentionally smaller than their hard maximum, and paid
batch operations require a cost preflight.

## Residual risks

Browser engines resolve networking outside Python's socket-level DNS pinning, so rendered
workflows additionally rely on request interception and revalidation. Search and provider
APIs can change behavior or pricing. Generated recommendations can be wrong or stale.
Users should review high-impact changes and validate current provider documentation before
publishing or submitting data.
