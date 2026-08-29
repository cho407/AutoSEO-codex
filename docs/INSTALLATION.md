# Installation

## Install from the repository marketplace

```bash
codex plugin marketplace add cho407/AutoSEO-codex --ref main
codex plugin add autoseo@autoseo
```

Start a new Codex session after installation, then ask `@autoseo` for a page,
site, keyword, or report workflow.

## Verify the plugin

Resolve the installed AutoSEO directory as `<plugin-root>` and run:

```bash
<plugin-root>/scripts/autoseo doctor --json
```

`doctor` does not install packages or access the network. A `setup required` result
is normal until a workflow needs a Python helper.

## Optional analysis runtime

Run setup only when you want the bundled deterministic helpers. The standard
profile includes Playwright for conditional page rendering and Naver editing:

```bash
<plugin-root>/scripts/autoseo setup --profile standard
```

For browser-free analysis:

```bash
<plugin-root>/scripts/autoseo setup --profile lite
```

Install optional integrations only when needed:

```bash
<plugin-root>/scripts/autoseo setup --profile lite --with google
<plugin-root>/scripts/autoseo setup --profile standard --with report
```

Setup creates a dedicated isolated environment. Set `AUTOSEO_DATA_DIR` to a dedicated
subdirectory if you want to choose its location. Filesystem roots and the user home
directory itself are rejected.

## Optional no-cost first-party data

Some workflows can add evidence from a Google Search Console, Google Analytics,
CrUX, YouTube, or Bing Webmaster property that the user already owns. These sources
are optional: AutoSEO still produces a bounded public-data or local analysis without
them. Keep credentials in environment variables or user-owned configuration and never
place them in this repository. AutoSEO does not configure a service that requires a
separate subscription.

Optional Naver Search and DataLab evidence reads `NAVER_CLIENT_ID` and
`NAVER_CLIENT_SECRET` from the environment. Naver editing requires no writing API:
it opens PC SmartEditor ONE in a dedicated visible Chromium profile. The user logs
in and completes two-factor authentication or CAPTCHA manually. Run
`@autoseo naver-editor doctor`, then `@autoseo naver-editor learn` before the first
release-candidate draft test.

`autoseo-unlighthouse` additionally requires an already installed `unlighthouse-ci`
binary on `PATH`, or an absolute executable path in `AUTOSEO_UNLIGHTHOUSE_BIN`.

## Uninstall

Remove the plugin through Codex. Reports and runtime data are intentionally retained so
an uninstall cannot silently delete user work. Delete those user-owned directories only
after reviewing their contents.

The Naver profile, checkpoints, compatibility map, and diagnostics also remain under
`AUTOSEO_DATA_DIR`. Review drafts and sign-in state before deleting them.
