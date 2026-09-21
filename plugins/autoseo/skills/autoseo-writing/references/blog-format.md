# Consistent blog formatting

Use for **new** Naver/Tistory articles. This is an editorial default, not a ranking
requirement. Do not restyle a published post, overwrite a saved document or migrate
an in-progress checkpoint unless requested. User choices override the preset.

## Quality floor and personal presentation profiles

The format preset controls safe document alignment and hierarchy. The separate
`blog_style.py` catalog controls optional editorial direction. `balanced-editorial`
is the universal fallback; `tactile-howto` is a personal profile that may add a
warm paper/grid treatment, centered short prose, a square cover and 4:5 procedure
images. It was abstracted from an inspected Korean how-to reference, but it is not
the reference's artwork, a Naver ranking rule or a default for other authors.

Every profile keeps the same quality floor: answer first, dated source ledger,
fact-preserving edits, readable mobile type, privacy-redacted evidence images and
honest provenance. A profile can guide composition and tone, but it cannot prove
that an image caused a view or guarantee search exposure. Put the selected profile
name in a generated image brief's `style_profile` so the prompt and visual review
remain bound to the document.

## Select once per article

New blog drafts use `layout_preset: "blog-centered"`. Reuse an explicit saved/requested
preference instead. Use `article-readable` when the user asks for a left-aligned
article, or `none` for no automatic styles. Keep the same preset through the whole
article; do not choose different fonts, colors or header treatments per section.

| Element | blog-centered default | article-readable |
|---|---|---|
| Intro and ordinary paragraphs | Center, 16 px, line spacing 1.8 | Left, same type scale |
| Section H2 / H3 | Center, bold, 24 / 20 px, one neutral color | Left, same hierarchy |
| Short quote / key takeaway | 18 px; bold only for a summary | Left, same hierarchy |
| Image caption | Center, 14 px, muted gray | Same |
| Source / detailed explanation | Left, 14 / 16 px respectively | Same |
| Lists, tables and code | Left; preserve useful structure | Same |

Naver uses supported native heading/quote and formatting controls. Tistory uses
semantic headings and safe inline CSS, with a consistent divider under headings,
paragraph margins and subdued quote treatment. The two platforms need not look
pixel-identical. Do not claim an exact native decoration, font or live layout was
verified based only on a local fixture. A missing/ambiguous control stops for
guidance rather than guessing or silently losing formatting.

Use the editor/site font by default; do not install fonts or force a remote font.
Small accent choices are acceptable when a supplied brand requires them, but avoid
rainbow headings, repeated emoji labels, underlining whole paragraphs or turning
each section into a different template.

## Paragraph rhythm and structure

- Break prose by meaning into short blocks, usually 1–3 sentences. On mobile,
  inspect density instead of enforcing a fixed character count per visual line.
  Do not insert line breaks inside names, numbers or URLs to fake mobile wrapping.
- Center short conversational prose. Put long analysis, procedures and source
  notes in `format_role: "detail"` / `"source"`; these remain left aligned even in
  the centered preset. Use real lists/tables where supported, not spaces for columns.
- Use H2 for major sections and H3 for subtopics, not a quote widget for every
  heading. Keep headings concise and parallel, without a mandatory section count.
- Lead with a brief answer or hook, then meaningful sections, evidence/media near
  the relevant claim, and a short takeaway. This is a flexible reading rhythm,
  not identical wording or the same outline for every article.
- Use actual paragraph separation and spacing. Do not add repeated empty blocks,
  long runs of `<br>`, copied ornamental separators or rasterized body text.

## Document contract

Both document formats accept `layout_preset`. Paragraphs optionally accept
`format_role`: `intro`, `body`, `summary`, `caption`, `source`, `detail`. Headings use
their existing type/level. Explicit block `style` fields override just those preset
values, including `bold: false` and a different alignment. Text and ordering are
never changed by the formatter.

Defaults are resolved during compilation, not written into each input block. This
keeps a changed preset from retaining old defaults as accidental overrides. The
preset is part of the document hash; changing it requires a new/reconciled draft,
not a silent resume of old styling. Omitted presets keep legacy documents unchanged.

For styled Tistory drafts use `format: "auto"` or `"html"`; auto selects HTML.
Explicit Markdown plus styles is rejected because the layout would be lost. Do not
silently change a user's explicit Markdown requirement: offer plain Markdown with
`layout_preset: "none"` and no block styles, or styled HTML. Never pass arbitrary
HTML/CSS from untrusted content; use the document's allowlisted style fields.

No extra helper call is needed if the writer already included the preset. To apply
one to a local existing document on request, save a **new** file:

```text
<plugin-root>/scripts/autoseo run blog_format.py presets
<plugin-root>/scripts/autoseo run blog_format.py apply naver <document.json> --preset blog-centered --output <new-document.json>
<plugin-root>/scripts/autoseo run blog_format.py apply tistory <document.json> --preset article-readable --output <new-document.json>
```

The helper does not open a browser, rewrite the prose, change publication settings
or publish. For a prepared document, the editor's compact `plan` reports preset and
format. Preserve content hashes, save receipts and per-post publication approval.

Review one representative heading, paragraph, source note and image caption at
desktop/mobile width before saving a new style. Reuse that choice for the remaining
sections; do not re-inspect the full editor after every formatting click.
