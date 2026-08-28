# No-subscription backlink evidence

No public source provides a complete, real-time backlink index. AutoSEO combines
several inspectable sources and reports coverage rather than inventing totals.

## Common Crawl domain graph

- Public and downloadable without an account.
- Useful fields: crawl presence, PageRank rank, harmonic-centrality rank, host
  count, graph release, and capture age.
- Limitations: periodic releases, incomplete coverage, and no guarantee that every
  individual incoming link can be enumerated from the bundled lookup.

## Codex-native public research

- Search for the domain, brand, quoted claims, research titles, assets, and known
  citations.
- Record the exact query, market, capture time, result URL, and source page.
- Treat the output as a discoverable sample, never as total link count.

## Verified-site search data

When the user already owns and authorizes a no-cost search property, use its link
or performance evidence. This cannot be used to inspect arbitrary competitors.

## User exports

Accept CSV or JSON exports supplied by the user. Preserve the export date and
source. Validate columns and avoid silently mixing different collection methods.

## Direct verification

For every candidate source URL, fetch the public page and verify:

- target URL or target-domain link;
- anchor text and surrounding context;
- link attributes;
- source status and redirects;
- target status;
- capture time.

## Local change history

Save a baseline with `backlink_history.py snapshot`, then compare a later capture.
New and lost labels apply only to those snapshots. A missing record can reflect
discovery coverage, so verify before acting.

## Reporting rule

Keep graph rank, discovered link sample, verified links, first-party evidence, and
historical changes in separate sections. Missing data is `not measured`, never zero.
