# Blog presentation standard

AutoSEO separates a reusable quality floor from an author's optional presentation
profile. The floor should remain stable across models, topics and platforms; a
profile changes rhythm and visual direction without pretending to be a ranking
formula.

## Reference-derived observations

The supplied Korean utility/how-to reference was useful for the following
observable traits:

- answer and current rule near the beginning;
- a concrete title naming the task and affected service or benefit;
- short centered prose with concise section headings;
- official sources, tables and a freshness note for time-sensitive claims;
- a square cover followed by procedure images, each with one real app action;
- an actual screen in a clean frame with one precise circle/arrow callout.

These observations do not prove that a single image caused views. A post-level
inflow report is a small sample and cannot isolate image, title, freshness, topic
demand or distribution effects.

## Universal quality floor

Every new post should have an answer-first introduction, short readable sections,
a dated source ledger, fact-preserving edits, mobile-readable assets, privacy-
redacted evidence and honest provenance. Real screenshots require authorization;
invented UI, statistics, logos and testimonials are rejected. Review the rendered
document at desktop and 375px mobile width before editor handoff.

`balanced-editorial` represents this floor and leaves the universal document preset
unchanged.

## Personal `tactile-howto` profile

The optional local profile is intended for the author's own practical Korean
how-to posts:

- `blog-centered` layout, centered short prose and centered quote-like headings;
- a square tactile cover and 4:5 step images;
- cream/grid paper, navy (`#253B50`) and coral (`#E86D4E`) accents;
- one short headline, one real screenshot or source photo and one purposeful
  callout per image;
- comparison tables/checklists in the document, not dense rasterized cards;
- a closing checklist and source/freshness note.

This is a local presentation choice, not a promise of exposure or engagement. It
does not override evidence, privacy, editor safety or per-post approval.

```text
<plugin-root>/scripts/autoseo run blog_style.py presets
<plugin-root>/scripts/autoseo run blog_style.py status
<plugin-root>/scripts/autoseo run blog_style.py set tactile-howto --confirm
```

The local file contains only the selected profile and confirmation time. Generated
image briefs should include `"style_profile": "tactile-howto"` so the direction is
included in the prompt digest and cannot silently change after review.
