# Naver SmartEditor ONE Compatibility

This matrix describes AutoSEO 0.4.0-rc.1 support for the PC Naver Blog
SmartEditor ONE. `automatic` means a deterministic adapter and checked local
regression path exist. `guided` means AutoSEO opens the exact control and waits
for the user to choose or review a visible candidate. `unavailable` means the
feature is deliberately not claimed.

All live-editor rows remain release-candidate status until the manual checklist
at the end of this document is completed on a user-owned test draft. Run
`@autoseo naver-editor learn` first when the editor UI has changed.

## Automatic

| Feature ID | Supported outcome |
|---|---|
| `title` | Fill a uniquely identified title field |
| `paragraph` | Insert a paragraph block |
| `heading` | Insert an H2/H3-style subheading block |
| `quote` | Insert a quote block |
| `divider` | Insert a divider and verify a new component |
| `font-family` | Apply an explicitly named font option |
| `font-size` | Apply an explicitly named size |
| `bold` | Toggle bold formatting |
| `italic` | Toggle italic formatting |
| `underline` | Toggle underline formatting |
| `strikethrough` | Toggle strikethrough formatting |
| `text-color` | Apply an explicit `#RRGGBB` text color |
| `alignment` | Apply left, center, right, or justified alignment |
| `line-spacing` | Apply an explicitly named line-spacing option |
| `superscript` | Toggle superscript formatting |
| `subscript` | Toggle subscript formatting |
| `special-character` | Insert the exact Unicode character from the document |
| `link` | Link anchor text that occurs exactly once in its block |
| `photo` | Upload one bounded local image |
| `group-photo` | Upload 1-20 explicit image paths as a group |
| `video` | Upload one bounded local video |
| `multi-attach` | Upload 1-20 explicit attachment paths |
| `external-link` | Insert a validated public HTTP(S) URL component |
| `file` | Upload one bounded local file |
| `schedule-component` | Insert an in-article schedule component |
| `table` | Create a bounded table and fill its cells |
| `equation` | Insert an explicit equation expression |
| `tags` | Apply up to 30 validated tags |
| `category` | Select the exact category named in final settings |
| `visibility` | Select public, neighbors, or private visibility |
| `search-allowed` | Set the search exposure switch to the requested value |
| `comments-allowed` | Set the comment switch to the requested value |
| `sympathy-allowed` | Set the sympathy switch to the requested value |
| `ccl` | Select the requested CCL setting |
| `share-allowed` | Set the sharing switch to the requested value |
| `draft-save` | Save only after a document-bound draft approval |
| `publish` | Click once only after a fresh final-settings approval |
| `schedule-publish` | Schedule once only after time validation and fresh approval |

## Guided

| Feature ID | Why user selection remains visible |
|---|---|
| `title-background` | Background layouts and personal assets can present account-specific choices |
| `spellcheck` | Corrections can change meaning and require editorial judgment |
| `photo-replace` | The target photo and replacement result must be visually confirmed |
| `photo-properties` | Layout and property choices depend on the selected image |
| `photo-editor` | Crop, filter, and adjustment results require visual review |
| `sticker` | Sticker candidates are visual and account/UI dependent |
| `place` | Search can return multiple businesses with similar names |
| `template` | Available templates depend on the current account and editor version |
| `library` | Personal library contents must remain user-selected and local to the account |
| `talktalk` | The correct user-owned TalkTalk channel must be selected visibly |

## Unavailable

No feature in the current official PC Blog editor catalog is silently omitted.
Rows that cannot be verified safely are downgraded to `guided`; a missing or
ambiguous control stops instead of being treated as successful. This does not
extend support to Naver Cafe, Place, Smart Store, mobile editors, bulk posting,
automatic comments, sympathy, neighbor actions, or login bypass.

## Locator and resume contract

Controls are resolved in this fixed order:

1. accessibility role and accessible name;
2. exact Korean screen label;
3. documented shortcut;
4. versioned DOM fallback.

Every operation has a stable ID, precondition, and postcondition. The checkpoint
stores the source hash and completed IDs but never the title or article body. A
stale locator is resolved once; a missing, duplicate, or changed control stops and
leaves a local diagnostic. Resume requires the same document hash and a verified
Naver draft URL.

## Manual release checklist

- [ ] Login, two-factor authentication, and CAPTCHA remain entirely manual.
- [ ] Basic text, heading, quote, divider, and all formatting controls work.
- [ ] Photo, grouped photo, video, link, and file attachment work within bounds.
- [ ] Place, schedule component, table, equation, template, library, sticker, and TalkTalk paths stop or complete as classified.
- [ ] Draft save succeeds and the browser remains open for review.
- [ ] A separately approved publish succeeds once without duplicate posting.
- [ ] A separately approved scheduled post preserves the requested timezone-aware time.
- [ ] Cookies, profile data, article text, and diagnostics are absent from logs, Git, CI, and the release archive.

Until all items pass against the live editor, keep the plugin version at
`0.4.0-rc.1`; promote to `0.4.0` only after recording the date and editor surface
used for validation.
