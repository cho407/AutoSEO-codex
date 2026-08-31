# Tistory editor compatibility

This reference separates deterministic functionality from controls that must be
verified against the live, user-owned PC editor before a stable release.

## Current coverage

| Capability | Status | Verification |
|---|---|---|
| TistoryDocument validation | automatic | Local schema and regression tests |
| Markdown rendering | automatic | Local renderer; no account required |
| HTML rendering and escaping | automatic | Local renderer; no raw script blocks |
| Main-person and bystander mosaic plan | automatic | Local frontal/profile detection plus explicit overrides |
| Original preservation and EXIF/GPS stripping | automatic | Private derived file; original overwrite rejected |
| Dedicated Tistory browser profile | automatic | Permissions and host allowlist tested |
| Kakao login, 2FA, CAPTCHA | guided | User completes these in the visible browser |
| Markdown/HTML mode selection | automatic candidate | Accessibility names, Korean labels, then versioned DOM fallback |
| One-buffer title/body/tag draft write | automatic candidate | Content hash and postconditions checked |
| Image upload and hosted URL capture | automatic candidate | One upload attempt; ambiguous result stops |
| Category, visibility, comments | automatic candidate | Applied only in the final publish dialog |
| Draft save | automatic candidate | Requires an observable save postcondition |
| Publish and schedule | approval-gated | One click after per-post approval; no unclear-result retry |
| Protected-post password | unavailable | Secret-bearing workflow intentionally excluded |
| Animated GIF face mosaic | unavailable | Use a static derivative or explicitly disable privacy processing |
| Bulk posting and engagement automation | unavailable | Outside product safety scope |

`automatic candidate` means the implementation and mock editor regression tests are
complete but the selector map must be refreshed with `learn` and manually checked
against a live editor for this release. A missing or duplicate match is a failure,
not permission to guess.

## Live release checklist

1. Run `doctor`, then `learn`, using a dedicated test blog and visible browser.
2. Confirm Markdown and HTML mode selection without content transformation after
   insertion.
3. Upload one ordinary image and one multi-person privacy derivative. Verify exactly
   one hosted URL per upload and inspect the final alt text and caption.
4. Interrupt after one completed operation, resume from the saved draft URL, and
   confirm that neither the upload nor body is duplicated.
5. Save one private draft. Inspect title, body, code, table, image, tags, and category.
6. With explicit per-post approval, publish one test post and schedule one future
   post. Confirm that an indeterminate result cannot be retried by the tool.
7. Confirm that the browser profile, checkpoints, source images, derivatives, and
   diagnostics are absent from logs, Git, CI artifacts, and release archives.

## Maintained evidence

- Tistory's official editor documentation describes Basic, Markdown, and HTML modes:
  <https://notice.tistory.com/2482>
- The official editor FAQ describes GitHub Flavored Markdown as its Markdown basis:
  <https://notice.tistory.com/2484>
- Tistory announced that Open API posting, editing, attachment, and comment operations
  ended by February 2024:
  <https://notice.tistory.com/2664>

These sources establish the supported user-facing modes, not a stable automation API.
The local compatibility map is therefore versioned and live validation remains a
release gate.
