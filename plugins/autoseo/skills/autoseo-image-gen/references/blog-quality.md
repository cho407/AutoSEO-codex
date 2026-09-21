# Blog image quality floor

Use for generated Naver/Tistory hero, explainer and OG assets, including with small
writing models. The image model is separate from the writer. Never silently switch
providers, purchase credits or add subscriptions. These are AutoSEO editorial
defaults, not Naver ranking requirements or an aesthetic guarantee.

## Start from the article, not a slide template

When prior posts are in scope, inspect 3–5 relevant posts once: cover treatment,
photography/illustration, text density, material/light, aspect ratios and image
placement. Summarize **keep / avoid / uncertain**. The user's latest criticism
overrides an old pattern; do not infer that every previous AI card is a favorite.
Keep private examples and blog identifiers out of the public plugin. A reference
URL alone does not mean its image was inspected or that reuse is licensed.

Choose an image's job before choosing a style:

| Job | Prefer | Avoid |
|---|---|---|
| Opening/hero | A specific subject or editorial scene; an intentional short-title cover when requested | Repeating the whole article title as a default slide |
| Product, service or event evidence | User-authorized photos or appropriately licensed actual source imagery with attribution | Invented product UI, generated launch photos, fictional first-hand experience |
| Conceptual explanation | A meaningful scene, tactile illustration or visual metaphor labeled as conceptual | Generic 3D icons and a grid of keyword boxes |
| Data/process relationship | A small accurate chart/diagram next to the relevant paragraph, only when it helps | A mandatory multi-box summary for every article |

The blog default is **social-card**, an Instagram-like editorial card-news
composition: one message, a short headline, optional brief support and a substantial
relevant photo/illustration. Strong typography, intentional panels and designed
backgrounds are welcome. Reject interchangeable report grids and dense bullets,
not the entire card format. Keep typography and palette consistent across a series,
but vary image scale and composition. Do not generate a whole carousel unless asked.

Paper texture, pencil marks, restrained hand lettering and collage are available
directions for an editorial cover. They are **not** a universal beige theme or a
substitute for subject matter. Match photography to the actual scene's color and
light. Retain enough detail and depth to feel like an image rather than empty UI.
An explicit `cover` can use a short checked title; text-free images are not the
only acceptable style. Do not rasterize long explanations or source footnotes.

Place supporting images near the prose they clarify. Do not stack a cover and a
summary card before the introduction by default. Vary purpose, not just color;
prefer one useful photo over several interchangeable cards. Image count and style
are editorial choices, not assumed ranking signals.

### Optional `tactile-howto` profile

When the writer has explicitly selected this personal profile, use the following
as a production target rather than a universal template:

- Use a 1:1 cover and 4:5 procedure images with a cream/grid paper base, navy ink,
  coral callouts and restrained handmade/collage texture.
- Keep one short handwritten-style headline per image. Pair a real official or
  user-authorized screenshot with a clean paper frame and one circle/arrow around
  the exact control being explained.
- Keep the article's short centered prose and quote-like section rhythm, but never
  rasterize paragraphs, sources or dense comparison tables into an image.
- Redact personal data, record the source/freshness note and disclose any AI-made
  cover. Never redraw an app interface, invent a badge or copy the reference art.

The profile is a local presentation choice. It does not change SEO/AEO/NEO scoring,
does not imply that the image caused a view, and must not replace the six visual
checks below.

## Compile one brief

Use `examples/blog-image-brief-v1.json`: `schema_version: 1`, factual `topic`, short
`title` (a short headline for social-card/cover), and a concrete `visual_subject`. Add concise
`art_direction` (material, light, composition, what to avoid) and `article_context`
(the adjacent section and what the image adds). Do not send the full article for
every image. These optional directions participate in the review's brief hash.

Defaults: `role: hero`, `layout: social-card`, `aspect_ratio: "1:1"`,
`theme: clean-editorial`, `palette: contextual`. Other layouts: editorial
illustration/scene, intentional cover, photo, or explicitly chosen card/steps.
Social-card/editorial/cover require `visual_subject`.
Card/steps are opt-in typography templates, not fallback defaults; they retain
sage/blue/clay palettes (sage if omitted), and steps needs 2–4 short ordered items.
Social-card, photo, cover and editorial requests cannot be rendered as local text cards.

Run `<plugin-root>/scripts/autoseo run blog_image.py plan <brief.json>` once. The
code adds these constraints independently of the writing model:

- Social-card defaults to 1600×1600, minimum 1200×1200. Optional `aspect_ratio: "4:5"`
  uses 1280×1600 (minimum 1080×1350). These are production choices, not platform rules.
  Other hero/explainer layouts default to 1600×900, minimum 1280×720. `"4:3"`
  uses 1600×1200 (minimum 1200×900), `"1:1"` uses 1600×1600 (minimum 1200×1200).
  Choose the ratio for the actual composition instead of forcing a slide. Ratio
  tolerance is 3%; OG remains 1200×630 (`"1.91:1"`), never an arbitrary crop.
- Static PNG/JPEG/WebP, ≤8 MiB/24 MP. Do not upscale merely to pass dimensions.
- One clear subject, coherent light/material/depth, useful negative space and 6%
  safe margins. Avoid interchangeable rounded-panel grids, decorative dashboards
  and empty canvases. Purposeful social-card panels and large legible type are
  allowed. No invented logos, pseudo-text or fake statistics.
- Editorial/photo title and subtitle are context, not image text. For an intentional
  cover, keep the title short and inspect each character. Use captions for detailed
  explanations; fix/remove bad lettering rather than replacing the whole image
  with a flat card. Do not invent a date, publication badge or source stamp.

Use the compiled prompt with the authorized host image tool. Use already inspected
references to guide visual traits, not to copy artwork or layouts. Do not require
generic corporate design websites when relevant user references already exist.
Real source images need provenance, reuse permission and an honest caption; a
source link is not by itself a reuse license. Do not redraw evidence with a model.

## Bounded quality loop

1. Generate once; run `blog_image.py check <brief.json> <asset>`. Technical checks
   return visual-review-required, **not accepted**. They do not measure aesthetics.
2. Open the actual asset at full size and 375px wide. Use the plan's
   `visual_check_guidance` for all six checks. Reject an unintended slide-like
   composition under `clean_composition`: interchangeable icon tiles, repetitive
   boxes, dense bullets or mostly empty space with no visual purpose. Do not reject
   a designed social-card/cover/diagram merely because it has a large headline or
   panels. Also inspect malformed anatomy/objects/pseudo-text, truthful
   details and safe crop. Compare numbers to the verified article/source ledger.
   Never mark unseen pixels as reviewed; blank high-resolution files cannot pass
   topic/composition inspection just because technical validation succeeded.
3. Allow at most **one regeneration** with a specific correction, only without
   additional purchase. Do not repeat research/rewrite the article for one image.
4. If inadequate, use an available authorized real image, ask for a usable asset,
   or leave that optional image out with disclosure. Stop a required image's upload.
   Use local card/steps only for an **explicitly chosen** typography/process brief;
   do not change `layout` just to make the renderer accept a failed illustration.
5. Record six booleans in a checks JSON: `topic_match`, `clean_composition`,
   `legible_at_mobile`, `no_visual_artifacts`, `truthful`, `safe_crop`.

```text
<plugin-root>/scripts/autoseo run blog_image.py review <brief.json> <asset> --checks <checks.json> --reviewer agent-visual --output <review.json>
<plugin-root>/scripts/autoseo run blog_image.py check <brief.json> <asset> --review <review.json>
```

Use reviewer=user only for actual user inspection. Reviews are attestations, not
vision-classifier scores. False/missing checks cannot pass; changing the file or
brief invalidates its hash binding. Exit codes: 0 plan/ready, 3 rejected or pending
review (render may have created an image), 2 validation/dependency error. Do not
blindly retry code 3.

## Explicit free local template

```text
<plugin-root>/scripts/autoseo run blog_image.py render <brief.json> --output <new-asset.png>
```

Only a brief with `layout: card` or `layout: steps` is accepted. The default example
is social-card, so `render` intentionally refuses it; use `plan` and the available
host image tool. Templates are not higher-quality substitutes for photography or
tactile covers. Uses the existing optional image runtime/Pillow, local OS Korean fonts or explicit
`--font <licensed-local-font>`. No API/model/font download. Missing glyphs/overflow
stop; fonts are never shrunk into tiny captions. Files are never overwritten.
Rendered cards still need visual review and must not be described as photographs.

## Editor handoff

Include **every generated asset** in NaverDocument/TistoryDocument's
`generated_images` list: `{ "path": "<asset>", "brief": <brief-object>,
"review": <review-object> }`, alongside its normal photo/media block. Both drivers
block unattached, changed, rejected or unreviewed declared assets before upload.
Metadata participates in document hashes. Never omit it to bypass a failed check.
Legacy/user-photo documents remain compatible; pixels alone cannot prove source,
so undeclared legacy files are not automatically certified. Review privacy
derivatives too if mosaicing changes the final visible content.

The automated profile covers hero/explainer/OG, including social-card 1:1/4:5.
For other vertical infographics/product/custom ratios, deliver the reviewed local asset and disclose
that automated quality-metadata handoff needs a supported profile extension. Never
mislabel a custom image as a hero to bypass this boundary.

[Google Images](https://developers.google.com/search/docs/appearance/google-images)
supports relevant high-quality images and contextual alt text.
[Discover](https://developers.google.com/search/docs/appearance/google-discover)
discusses large images/cropping. Neither guarantees Naver exposure; image checks
never add artificial SEO/NEO points.
