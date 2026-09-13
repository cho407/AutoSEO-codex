# SmartEditor ONE structure and fast paths

This reference records only reusable editor chrome and control structure. It
contains no blog name, document title, article text, attachment path, account
identifier, cookie, or session value.

## Observation scope

- Surface: Naver Blog PC SmartEditor ONE, Korean UI
- Observed: 2026-09-14 (Asia/Seoul)
- Evidence: one live accessibility-tree observation plus the distributed
  catalog's versioned DOM fallbacks
- Meaning of `observed`: the control name was present on the live editor
- Meaning of `live verified`: an operation and its postcondition were exercised
  through the Playwright driver; accessibility presence alone does not qualify

## Stable regions

| Region | Observed controls or anchor | Automation use |
|---|---|---|
| Top command bar | `저장`, `임시저장된 글 보기`, `발행`, `더보기` | Save and guarded publication boundaries |
| Component toolbar | `사진 추가`, `MYBOX 추가`, `동영상 추가`, `스티커 추가`, `인용구 추가`, `구분선 추가`, `링크 추가`, `파일 추가`, `일정 추가`, `소스코드 추가`, `표 추가`, `수식 추가`, `장소 추가`, `내돈내산 상품 첨부`, `글감 검색 열기`, `내 클립 열기`, `라이브러리 열기`, `템플릿 열기` | Component insertion |
| Format toolbar | `서체 변경`, `글자 크기 변경`, `정렬 열기`, `특수문자 열기`, `번역`, `맞춤법` | Bounded formatting operations |
| Document | title block followed by `.se-main-container` | Title and body scoping |
| Save acknowledgement | `임시저장이 완료되었습니다.` | One fresh save receipt; never reopen the draft list |

## Catalog-owned DOM fallbacks

These selectors are code-owned constants in `data/naver-editor-features.json`.
A learned compatibility file may choose among them but cannot add a selector.

| Feature | Selector | Expected region |
|---|---|---|
| Title | `.se-documentTitle .se-text-paragraph` | Main document frame |
| Editor root | `.se-main-container` | Visible frame containing editable descendants |
| Photo | `button[data-name='image']` | Main document frame |
| Video | `button[data-name='video']` | Main document frame |
| File | `button[data-name='file']` | Main document frame |
| Draft save | `button[data-click-area='tpb.save']` | Main document frame |
| Publish settings | `button[data-click-area='tpb.publish']` | Main document frame; guarded publish flow only |

The title and draft-save controls use shipped fast hints because they are the
two controls needed by `revise-title`. Each hint must resolve to exactly one
visible element. Zero matches fall back to the bounded resolver; multiple
matches stop the run as ambiguous.

## Resolution order

1. Load a compatibility map only when origin, catalog hash, browser signature,
   targeted UI signature, and seven-day freshness all match.
2. Try the learned frame, scope, strategy, and catalog-approved name once.
3. Try a shipped catalog fast path when one exists.
4. Fall back to exact locale-ranked role/name and exact text labels.
5. Use a shortcut only when an editor input is positively focused.
6. Try the catalog-owned DOM fallback.
7. Stop when a control is missing or ambiguous.

Routine calls use Playwright locators and targeted DOM checks. They do not take
screenshots, serialize the full accessibility tree, or send editor structure to
a model. Screenshots remain diagnostic artifacts only after an actual failure.

## Fast title revision contract

`revise-title` requires the exact current title and a replacement title. It:

1. selects exactly one already-open Naver editor tab;
2. resolves the title through the learned or shipped fast route;
3. verifies the exact current title before writing;
4. fingerprints the rendered body in memory;
5. replaces the title with exact Unicode input;
6. confirms the body fingerprint did not change;
7. clicks draft save once;
8. requires one new save acknowledgement; and
9. disconnects from an externally owned CDP browser without closing it.

The command never reads the saved-draft list and does not persist the title or
body in compatibility data.

## Persistent Chrome boundary

CDP attachment is restricted to a credential-free loopback HTTP endpoint and
exactly one open Naver editor tab. The browser must use a dedicated non-default
Chrome data directory. AutoSEO does not launch, close, clone, export, or inspect
the profile when attaching. It only controls the selected editor page for the
requested operation.
