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

## Optional local profile file

`balanced-editorial` is the only shipped profile. To use another presentation
direction, review an explicitly chosen private `BlogStyleLocalProfile` JSON stored
outside the repository and cache with mode `0600`, then select it locally:

```text
<plugin-root>/scripts/autoseo run blog_style.py presets
<plugin-root>/scripts/autoseo run blog_style.py status
<plugin-root>/scripts/autoseo run blog_style.py set-file <profile.json> --confirm
```

The local selection is checksum-bound to the file. A profile does not promise
Naver/Google exposure, clicks, citations, model training or a fixed view count, and
never overrides source accuracy, privacy, editor safety or per-post publication
approval.

## Boundaries

The profile does not promise Naver/Google exposure, clicks, citations, model
training or a fixed view count. It is not applied to another author's blog unless
they select it, and it never overrides source accuracy, privacy, editor safety or
per-post publication approval.
