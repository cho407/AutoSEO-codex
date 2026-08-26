# Command Guide

AutoSEO is prompt-driven. Use `@autoseo` followed by the outcome you want; Codex routes
the request to the smallest matching skill.

| Intent | Example |
|---|---|
| Full audit | `@autoseo Audit https://example.com and prioritize the first 30 days.` |
| One-page review | `@autoseo Review this product page's technical SEO, content, and schema.` |
| GEO review | `@autoseo Evaluate this site for AI-search citation readiness.` |
| Content brief | `@autoseo Create a sourced content brief for “zero-trust backups”.` |
| Topic cluster | `@autoseo Build a SERP-overlap topic cluster and internal-link plan.` |
| Local SEO | `@autoseo Audit this location page and its local business schema.` |
| International SEO | `@autoseo Validate the hreflang plan in this repository.` |
| Ecommerce | `@autoseo Review these product pages for merchant and structured-data issues.` |
| Regression | `@autoseo Compare this page with its saved SEO baseline.` |

## Runtime commands

```text
<plugin-root>/scripts/autoseo doctor --json
<plugin-root>/scripts/autoseo setup [--skip-browser]
<plugin-root>/scripts/autoseo run <allowlisted-script.py> [arguments]
```

The runtime does not accept arbitrary scripts, extension paths, or shell commands.
External writes such as IndexNow submission are never implied by a general audit prompt.
