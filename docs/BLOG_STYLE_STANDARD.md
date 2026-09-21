# Blog presentation standard

AutoSEO separates a reusable quality floor from an author's optional presentation
profile. The floor is the part that should remain stable across models, topics and
platforms; a profile changes the article's rhythm and visual direction without
pretending to be a ranking formula.

## What the inspected reference supports

The supplied Korean utility/how-to post was reviewed as an editorial reference.
Its strongest observable traits were:

- the answer and the current rule appear early;
- the title names the concrete task and the affected service or benefit;
- short centered prose is broken up by strong, concise section headings;
- official sources, tables and a freshness note support time-sensitive claims;
- the cover establishes the topic, while each following image explains one real
  app action;
- procedure images use an actual screen, a clean frame and one clear circle/arrow;
- the cover is square and the procedure images are portrait, so each image has a
  distinct job rather than being a stack of interchangeable cards.

These are editorial observations, not proof that any single image caused the
article's views. A post-level inflow report is a small sample and cannot isolate
image, title, freshness, topic demand or distribution effects.

## Universal quality floor

Every new post should pass these checks:

1. Answer-first introduction and a clear reader outcome.
2. Short paragraphs, predictable heading hierarchy and mobile-readable type.
3. Material claims tied to a source, observation date, market and language.
4. Facts, personal experience and editorial inference kept separate.
5. Real evidence images only when the user has permission; no invented UI,
   statistics, logos or testimonials.
6. Personal data removed from screenshots; asset provenance and AI disclosure kept.
7. One final desktop/mobile review of the actual rendered document.

The quality floor is represented by `balanced-editorial` and leaves the existing
universal document preset unchanged.

## Personal `tactile-howto` profile

The optional local profile is intended for the author's own practical Korean
how-to posts:

- `blog-centered` layout, centered short prose, quote-like centered section
  headings, about 16px body text and generous line spacing;
- a square tactile cover; 4:5 step images;
- cream/grid paper, navy (`#253B50`) and coral (`#E86D4E`) accents;
- one short headline per image, one real screenshot or source photo, and one
  purposeful callout;
- small comparison tables/checklists in the document, not dense rasterized cards;
- a closing checklist and a source/freshness note.

The profile is stored only as a local selection:

```text
<plugin-root>/scripts/autoseo run blog_style.py presets
<plugin-root>/scripts/autoseo run blog_style.py status
<plugin-root>/scripts/autoseo run blog_style.py set tactile-howto --confirm
```

The local file contains the profile name and confirmation time only. It never
contains article bodies, private URLs, images, cookies or account identifiers.
Generated image briefs should include `"style_profile": "tactile-howto"`; the
profile is then included in the prompt digest and cannot silently change after
visual review.

## Boundaries

The profile does not promise Naver/Google exposure, clicks, citations, model
training or a fixed view count. It is not applied to another author's blog unless
they select it, and it never overrides source accuracy, privacy, editor safety or
per-post publication approval.
