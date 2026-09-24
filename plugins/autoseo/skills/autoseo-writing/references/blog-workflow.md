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
2. A supplied topic controls the article, even when a dashboard or public trend
   appears more popular. A URL supplied for improvement is not automatically a
   no-topic request: retain the page's established subject and intent. Only when
   there is no supplied or established topic, identify the blog's dominant subject
   and intended audience from those titles/categories. Compare candidates within
   that scope; if no stable subject is observable, compare across the target market
   and language. Never force an unrelated trend into the blog or target page.
3. For a requested Naver blog article or topic discovery with no supplied or
   established topic, a relevant, current Creator Advisor topic may be a
   high-priority shortlist signal when the owner has authorized that blog's account
   view. Do not require a second topic-discovery request for an open-topic article.
   Inspect it only from an owner-provided export/screenshot or a visible read-only
   page after the owner supplies the exact target blog URL (or current Creator
   Advisor URL), or authorizes discovery for the current blog, and completes login
   themselves. The no-scraping rule prohibits automated extraction, private
   endpoints, cookies, and login automation; it does not prohibit bounded visible
   inspection. Never use API keys or billing for Creator Advisor, and keep account
   identifiers and URLs outside the repository and distributable output.
4. After shortlisting a candidate, begin a separate topic-to-public-research step
   using `autoseo-search-data`'s public category trend collection for current trends
   in that subject. Its `trend_collect.py` helper reuses one public RSS fetch across
   categories; supplement the short global feed with actual category web research.
   A Creator Advisor candidate may seed a public keyword query, but its account URL,
   export, screenshot, label/rank, order, or window must not enter `TrendCollection
   v1`, numeric demand, velocity, or aggregate ordering.
   Distinguish `observed-surge-single-provider` from current topics with `unmeasured`
   demand. An empty category is not permission to substitute unrelated headlines.
   Record market, language, source URLs,
   comparable trend signals, and observation/publication times as `TrendEvidence v1`;
   run `trend_evidence.py analyze <trend-evidence.json>` once. Default freshness is
   24 hours for breaking topics and 7 days for sustained interest. Require at least
   two independent source groups. Prefer the strongest corroborated current demand
   or growth among observed candidates when comparable demand data exists; otherwise
   select by topic relevance and verified freshness and disclose unmeasured demand.
   Do not present incomparable metrics or a small sample as an absolute global #1.
   Creator Advisor cannot satisfy this gate or appear in the evidence/metrics: use
   fresh primary facts plus at least one independent public source. Keep any label,
   rank, window, capture time, and verified blog scope only in an owner-approved
   working note as provenance, never as exact demand, Naver-wide rank, traffic,
   velocity, readiness, or observed visibility. If the account signal is inaccessible
   or its scope is unverifiable, continue with dated public evidence and mark only
   Creator Advisor unavailable; an unauthenticated SPA shell is not trend evidence.
5. If no candidate is confirmed, state the evidence limit and use the best-supported
   current topic; ask only if no defensible candidate exists. Research the selected
   topic's claims and reuse the same sources for prose and diagram labels.
6. Choose an existing matching category; if history is unavailable, use the closest
   existing general category. Store the choice in the document's category field.
   The current drivers apply categories in the final publication settings dialog;
   do not open that dialog merely to make a draft appear categorized or claim the
   remote category is set. Never create categories automatically.

## Body and visual deliverables

- Apply [blog-format.md](blog-format.md) once: new drafts use
  `layout_preset: "blog-centered"`, short centered prose, consistent H2/H3 styles,
  and left-aligned detail/source blocks. Explicit user styles win. Resolve the
  optional local presentation profile with `blog_style.py status`; the fallback is
  `balanced-editorial`, while a confirmed personal profile may refine the rhythm,
  image ratios and palette. Never force a personal profile onto another user or
  treat it as a ranking signal. Use `article-readable` for a requested left-aligned
  article; never force new defaults onto old drafts. Styled Tistory documents use
  `format: "auto"`/`"html"`.
- Write at least **1,500 body characters excluding whitespace** for a new Korean blog
  article. Count visible prose, headings, and lists; exclude title, markup, URLs,
  captions, alt text, and source ledger. Report the count after one final polish.
  Add useful examples or explanation if short, without padding or keyword repetition.
- Use a specific title, an answer-first introduction, readable sections, practical
  examples/steps or evidence, and a useful ending. Attribute material claims with
  source links. Adapt the structure to the topic.
- Plan a representative header/hero and a supporting visual near the relevant
  prose. The latter may be an actual product/source photo or a topic-specific
  illustration; it need not be an infographic. Use a process diagram, comparison,
  timeline or decision tree only when the relationship is clearer visually. Do not
  force a summary grid or pad the image count when no useful second image exists;
  disclose an omitted required asset instead of inventing evidence.
- Load `autoseo-image-gen` only for assets being generated. Use the host's available
  image tool for a social-card hero (one short message plus a relevant visual,
  1:1 or 4:5 by default). Keep 16:9/4:3 editorial/photo options when they fit the
  purpose or user preference. Use the tool for illustrative diagrams,
  or a deterministic diagram/chart renderer when exact labels/numbers matter. Export
  diagrams as blog-supported image files; Mermaid/code alone is not an inserted
  visual. A 2:3 infographic master can be used when a vertical layout helps; adapt
  dimensions to the actual content and available output sizes.
- Generate the actual assets and inspect them once before upload. Labels and numbers
  must match the sources; conceptual diagrams must match the article. Simplify or
  fix an incorrect image, and never fabricate data or treat a prompt as an image.
  If generation is unavailable, save the brief and report the missing asset.
- For default hero/explainer/OG assets, follow `autoseo-image-gen`'s
  `references/blog-quality.md`: one concise JSON brief with subject, visual direction
  and article context; visual-led social-card defaults, full-size/mobile
  inspection and six hash-bound visual checks. Clean does not mean a presentation
  slide. Preserve purposeful reference traits such as tactile covers or actual
  source photos without imposing them on every post. After one failed regeneration
  or an unavailable host tool, do not automatically replace imagery with a card.
  Local templates require an explicit card/steps choice. If a presentation profile
  is selected, copy its profile name into each brief's `style_profile`; otherwise
  use `balanced-editorial`. Declare all generated assets in `generated_images` with
  brief/review before editor handoff.
- Save images under the approved blog directory with descriptive filenames,
  dimensions, concise alt text, captions, and source/AI provenance where required.
  Preserve originals. Use local privacy derivatives for user photos as supported;
  do not send private pixels to an unapproved service.
- For Naver, use the hero as the first `photo` block with background `none`, followed
  by supporting image blocks near their related prose, not a stack of cards before
  the introduction. For Tistory, use local
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

Serialize the finished article once. The driver consumes JSON and shipped decision
rules without per-click model calls. Use `plan <document>` only for a needed preview
and `capabilities` only for unfamiliar features. Do not reread the full document,
catalog, checkpoint, DOM or screenshots for each operation. Normal results are
compact JSON; unknown UI/guided choices return to the user.

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
