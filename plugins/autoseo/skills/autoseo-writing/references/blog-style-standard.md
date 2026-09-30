# Blog presentation standard

AutoSEO keeps three layers separate: dated observations from a bounded public
result set, reusable editorial rules, and an optional individual presentation
profile. None of these layers is a ranking formula or evidence that a layout,
image, or topic caused visits.

## Dated, bounded observations

Describe the observation boundary before drawing a reusable lesson. Record the
query or topic, public result surface, language/market, device class, observation
date and time zone, sample size, and material limitations. For each usable item,
record its publication or update date when visible. Record a result position only
when it was actually visible and captured in that exact bounded result set; use
`observed_position`, never an inferred or durable rank.

Keep public-result observations distinct from observations of the owner's public
posts. Do not put private URLs, owner identifiers, account analytics, screenshots,
or unpublished material in this guide, the catalog, tests, or other distributable
files. A small, dated sample can suggest patterns worth evaluating, but it cannot
establish platform-wide rules or isolate the cause of ranking, exposure, clicks,
or visits.

Use this blank template only as a private working note; do not commit the completed
copy to the plugin:

```text
Observation scope
- observed_at:
- query_or_topic:
- public_surface / language_market / device_class:
- public_results_reviewed:
- owner_posts_reviewed:
- limitations:

Public result item
- publication_or_update_date:
- observed_position:                 # blank or "not recorded" unless captured
- answer_and_section_rhythm:
- media_role_and_placement:
- source_visibility:
- uncertainty:

Owner post item
- publication_or_update_date:
- answer_and_section_rhythm:
- media_role_and_placement:
- source_visibility:
- uncertainty:

KEEP
-
AVOID
-
UNCERTAIN
-
```

Classify the comparison before using it:

- **KEEP**: a useful, source-compatible pattern supported by the bounded sample
  and editorial judgment. Rewrite it as a general rule; do not copy wording,
  photographs, artwork, or a distinctive composition.
- **AVOID**: a quality, evidence, readability, or rights risk that should be
  guarded against.
- **UNCERTAIN**: an apparent association, inconsistent pattern, or missing fact.
  Do not promote it into a rule or causal claim without independent evidence.

## Reusable editorial floor

Every article should:

- answer the reader's main question near the beginning;
- prefer primary sources for material claims and show the applicable or source
  date, the date checked, and the reader's next action when timing matters;
- use native H2/H3 headings for sections instead of quote widgets;
- use short mobile-readable paragraphs while keeping detailed explanations,
  source notes, decision tables, and action blocks left aligned;
- preserve facts, label inference, redact private data, and retain honest source
  and media provenance.

Give every image a meaningful job tied to nearby prose, such as context, evidence,
process, comparison, or atmosphere. There is no fixed image quota. Do not use a
generic slide grid as the default cover, pad an article with decorative assets, or
turn detailed body prose into small rasterized text. Never invent a product photo,
interface, source screenshot, statistic, logo, or testimonial.

A request for a product-release photo must remain a request for an authentic,
eligible photo. If the required photo cannot be obtained or its use cannot be
cleared, hold the asset and report the gap. Do not silently replace it with a
conceptual card or model-invented product image.

## Source-media rights hold

"Official," "downloadable," or membership in a pressroom does not by itself grant
a license. Before using source media, check the evidence available for all of the
following:

- whether commercial use on a monetized blog is allowed;
- whether the specific source, membership status, and editorial use are eligible;
- whether cropping, overlays, annotations, or other modifications are allowed;
- what attribution, link, caption, or notice is required.

This checklist records evidence; it does not adjudicate copyright. If any material
condition is missing, ambiguous, or contradictory, place the asset on rights hold
and use no derivative until the user supplies permission or chooses an independently
eligible alternative. Preserve the original and the provenance record.

## Per-article photo direction

Photo-led treatment is an optional article-level choice, not a new profile. Express
it through the existing image brief fields: keep the requested `layout`, put the
concrete subject in `visual_subject`, put lighting/crop/material direction in
`art_direction`, explain its editorial job in `article_context`, select an
appropriate `aspect_ratio`, and retain `style_profile: "balanced-editorial"` unless
the user explicitly selected a local profile. Reference URLs are provenance
only and are never proof of usage rights. Do not downgrade `photo` or `cover` to a
card merely because local template rendering is available.

## Optional local profile file

`balanced-editorial` is the only shipped profile. To use another presentation
direction, review an explicitly chosen private `BlogStyleLocalProfile` JSON stored
outside the repository and cache with mode `0600`, then select it locally:

```text
<plugin-root>/scripts/autoseo run blog_style.py presets
<plugin-root>/scripts/autoseo run blog_style.py status
<plugin-root>/scripts/autoseo run blog_style.py set-file <profile.json> --confirm
```

The local selection is checksum-bound to the file. Include its selected
`style_profile` in each generated image brief so the direction is hash-bound and
reviewable; this still does not prove live rendering or performance.
