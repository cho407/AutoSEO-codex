# Blog article workflow

Use for a new blog article. The user's specific topic, format, language, and existing
authorization take precedence over these defaults.

## Topic and category before drafting

1. Reuse the known blog URL, writer preferences, categories, and recent-post context.
   When needed, inspect at most 10–20 recent public titles/category labels in one
   read-only pass. Retain only topic/category summaries; do not copy article bodies
   or unrelated account data. If this context is accessible only after login, open
   the one visible editor session early, let the user log in, then keep it open
   while completing research and assets. Never launch a second session for compose.
2. A supplied topic controls the article. With no topic, first identify the blog's
   dominant subject from those titles/categories. Compare current keywords within
   that subject; if no stable subject is observable, compare across all subjects in
   the target market/language. Do not choose a general trend first and force it into
   an unrelated blog category.
3. Use `autoseo-search-data` for current trends. Record market, language, source URLs,
   comparable trend signals, and observation/publication times as `TrendEvidence v1`;
   run `trend_evidence.py analyze <trend-evidence.json>` once. Default freshness is
   24 hours for breaking topics and 7 days for sustained interest. Require at least
   two independent source groups. Prefer the strongest corroborated current demand
   or growth among observed candidates, using relevance and freshness as tie-breakers.
   Do not present incomparable metrics or a small sample as an absolute global #1.
4. If no candidate is confirmed, state the evidence limit and use the best-supported
   current topic; ask only if no defensible candidate exists. Research the selected
   topic's claims and reuse the same sources for prose and diagram labels.
5. Choose an existing matching category; if history is unavailable, use the closest
   existing general category. Store the choice in the document's category field.
   The current drivers apply categories in the final publication settings dialog;
   do not open that dialog merely to make a draft appear categorized or claim the
   remote category is set. Never create categories automatically.

## Body and visual deliverables

- Write at least **1,500 body characters excluding whitespace** for a new Korean blog
  article. Count visible prose, headings, and lists; exclude title, markup, URLs,
  captions, alt text, and source ledger. Report the count after one final polish.
  Add useful examples or explanation if short, without padding or keyword repetition.
- Use a specific title, an answer-first introduction, readable sections, practical
  examples/steps or evidence, and a useful ending. Attribute material claims with
  source links. Adapt the structure to the topic.
- Include a representative header/hero image and at least one explanatory visual:
  a process diagram, comparison, timeline, decision tree, or compact concept summary.
  Choose a narrative summary illustration for topics without process/data. Add other
  supporting images only where they clarify the text.
- Load `autoseo-image-gen` only for assets being generated. Use the host's available
  image tool for the hero (16:9, target 1600 × 900). Use it for illustrative diagrams,
  or a deterministic diagram/chart renderer when exact labels/numbers matter. Export
  diagrams as blog-supported image files; Mermaid/code alone is not an inserted
  visual. A 2:3 infographic master can be used when a vertical layout helps; adapt
  dimensions to the actual content and available output sizes.
- Generate the actual assets and inspect them once before upload. Labels and numbers
  must match the sources; conceptual diagrams must match the article. Simplify or
  fix an incorrect image, and never fabricate data or treat a prompt as an image.
  If generation is unavailable, save the brief and report the missing asset.
- Save images under the approved blog directory with descriptive filenames,
  dimensions, concise alt text, captions, and source/AI provenance where required.
  Preserve originals. Use local privacy derivatives for user photos as supported;
  do not send private pixels to an unapproved service.
- For Naver, use the hero as the first `photo` block with background `none`, followed
  by explanatory image blocks near their related prose. For Tistory, use local
  `media` entries with `image` blocks. Avoid guided title backgrounds, decorative
  choosers, and image-edit dialogs in the normal login-only flow. Use an explicit
  thumbnail selector only when supported; an in-body hero is not proof of a separately
  selected representative thumbnail. Upload each asset once and report placement.

## One visible session through save

Research, write, and prepare media before opening Playwright whenever public/context
information suffices. Reuse an early session if login was needed for author context.
Load only the matching `autoseo-naver-editor` or `autoseo-tistory-editor` skill.
For a ready document, use its compose helper. If a session is already open, continue
with that session's guarded driver/automation; do not call a second CLI that opens
another profile. Do not run `learn` as a separate prerequisite.

The user handles login, 2FA, and CAPTCHA. Continue automatically when the editor is
ready. Detect control language from page/browser metadata; English UI never changes
Korean title/body language. Use Unicode `fill`/`insert_text` instead of physical key
spelling. Check the exact title once, with one scoped replacement if needed; preserve
body line breaks and tags. Never change the user's OS keyboard layout.

Validate the final document, show the compact article/media scope, compose, and save
once in the same session. Use only required media/text operations and the existing
content-integrity checks. Retain the fresh save acknowledgement and fingerprints,
report the result promptly, and leave the editor open for review. Do not close/reopen,
reload, repeatedly resave, or navigate elsewhere to test persistence. An unclear
upload/save stops for reconciliation; a local fixture pass cannot certify live UI.

Return actual save status, available draft link, character count, media placement,
chosen category (including whether applied or planned), and source ledger. Drafting
does not publish. If publication is later requested, refresh expired facts and obtain
the exact per-post final-settings approval required by the editor.
