# Installation

## Install from the repository marketplace

```bash
codex plugin marketplace add HarrisonCho407/AutoSEO-codex --ref main
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

Run setup only when you want the bundled deterministic helpers:

```bash
<plugin-root>/scripts/autoseo setup
```

To omit the optional Chromium download:

```bash
<plugin-root>/scripts/autoseo setup --skip-browser
```

Setup creates a dedicated isolated environment. Set `AUTOSEO_DATA_DIR` to a dedicated
subdirectory if you want to choose its location. Filesystem roots and the user home
directory itself are rejected.

## Optional providers

Provider skills do not auto-install connectors. Connect and authorize a supported
provider in Codex first, then invoke the matching AutoSEO workflow. Keep credentials in
environment variables or user-owned provider configuration; never place them in this
repository.

`autoseo-unlighthouse` additionally requires an already installed `unlighthouse-ci`
binary on `PATH`, or an absolute executable path in `AUTOSEO_UNLIGHTHOUSE_BIN`.

## Uninstall

Remove the plugin through Codex. Reports and runtime data are intentionally retained so
an uninstall cannot silently delete user work. Delete those user-owned directories only
after reviewing their contents.
