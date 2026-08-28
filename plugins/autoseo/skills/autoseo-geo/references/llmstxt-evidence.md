# `/llms.txt` — evidence-based reframe (June 2026)

## TL;DR

Google states that Google Search ignores `/llms.txt`. Other systems may use the
format for documented purposes, so report support per target system and date.
Never present the file as a Google ranking or citation lever.

## Primary-source evidence

| Source | Date | What they said |
|---|---|---|
| **Google AI optimization guide** (docs) | 2026-06-29 | You don't need llms.txt/AI-text files for Google Search (incl. generative AI features); doing so "won't harm (nor help) your visibility or rankings in Google Search, **as Google Search ignores them**." |
| **Other systems** | measured date | Record only documented consumption or behavior for that specific system. |

## Where it does matter

`llms.txt` is increasingly consumed by **AI coding agents** (Cursor,
Continue, Cline, Codex) when loading per-library documentation.
Mintlify auto-generates `/llms.txt` and `/llms-full.txt` for thousands
of developer-docs sites. For a developer-tooling site, publishing
`llms.txt` is a net win — it helps agents quote the docs accurately.

For other sites, create the file only when a target consumer documents a useful
workflow or the publisher has another concrete maintenance reason.

## How autoseo treats `llms.txt`

- `autoseo-geo` audits **report presence** of `/llms.txt` and `/llms-full.txt`.
- The audit notes whether the file is well-formed (Mintlify-style markdown).
- The audit explicitly does **not** assign citation-ranking weight to it.
- If the user asks to generate one, autoseo produces a minimal valid example
  and states that Google Search ignores it; any other claimed benefit must name
  the supporting system documentation.

## When this guidance changes

Update this file (and the autoseo-geo audit copy) when:

- Any major AI search system (Google AI Overviews, ChatGPT Search,
  Perplexity, Bing Copilot) publishes documentation confirming
  `llms.txt` consumption.
- A major answer system publishes primary documentation confirming consumption
  of third-party `/llms.txt` files.
- Google changes its published Search guidance.

Last verified: 2026-06-21.
