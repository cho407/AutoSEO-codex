# AutoSEO Privacy Policy

Effective date: 2026-08-31

AutoSEO is an open-source, locally executed Codex plugin. The publisher does not
operate an AutoSEO backend and does not receive prompts, analyzed pages, reports,
credentials, or usage telemetry.

## Data processed locally

AutoSEO may process URLs, downloaded public page content, user-selected files,
generated reports, audit baselines, and configuration required for a requested
workflow. Local runtime data is stored in the platform-appropriate AutoSEO data
directory or a directory explicitly selected by the user.

An optional `writing-identity.json` file can store the user-confirmed writer basis,
audience, content goal, tone, preferred and avoided terms, and platform defaults.
It is owner-readable only where the operating system supports permissions. It does
not store article bodies, research pages, credentials, or account cookies. AutoSEO
shows the proposed profile and requires confirmation before saving or replacing it.

For Naver Blog editing, the local data directory may contain a dedicated Chromium
profile, Naver cookies managed by Chromium, a UI compatibility map, hash-only
operation checkpoints, and failure screenshots. AutoSEO does not export cookies or
store the article title/body in its checkpoint. The user-selected source document
remains wherever the user placed it. Failure screenshots can visibly contain draft
or account information and should be treated as sensitive local files.

For Tistory editing, a separate local profile can contain Chromium-managed Kakao/
Tistory cookies, a UI compatibility map, operation hashes, upload states, hosted
media URLs needed to prevent duplicate uploads, and failure screenshots. Checkpoints
do not contain the article title, body, or original image path. Static-image privacy
processing creates user-only derivatives under `AUTOSEO_DATA_DIR/privacy-images`.
The original is preserved and EXIF/GPS metadata is stripped from the derivative by
default. Face boxes and image pixels are processed locally and are not sent to a
publisher-operated or third-party recognition service.

## External sources

When a user chooses an optional no-cost first-party source such as Search Console,
Google Analytics, CrUX, YouTube, or Bing Webmaster, data is sent directly to that
service under the user's account and is governed by its terms and privacy policy.
Public website, Common Crawl, RDAP, PageSpeed, and IndexNow requests likewise go
directly from the user's environment. AutoSEO does not proxy or retain requests on
publisher-controlled infrastructure and ships no separately billable data service.

On-demand trend collection requests a public Google Trends RSS feed directly,
sending the chosen market without provider credentials or browser cookies.
Supplementary category queries use the existing Codex-native web tools. Local
research records contain selected keywords, public source URLs/headlines, dates and
category reasons, not article bodies or account profiles. The collector only writes
a report when an output path is explicitly supplied; it does not enable recurring
collection. User-selected research queries should not contain private information.

Optional legacy Naver Search and DataLab requests go directly to Naver with keys read
from `NAVER_CLIENT_ID` and `NAVER_CLIENT_SECRET`. NAVER API HUB uses separate
`NAVER_API_HUB_CLIENT_ID` and `NAVER_API_HUB_CLIENT_SECRET` values and remains
disabled unless the user confirms a no-billing account through the documented local
guard. Those keys and the guard are not written to reports, checkpoints, or the
repository. SmartEditor automation operates only in the visible
user-owned browser profile; login, two-factor authentication, and CAPTCHA stay with
the user.

## Credentials

Credentials remain on the user's device or in the user's configured connection.
They must not be committed to this repository. AutoSEO redacts known credential
patterns from diagnostic output but users remain responsible for revoking any
credential that is accidentally disclosed.

## Retention and deletion

AutoSEO retains no publisher-side data. Users can delete local reports, caches,
audit history, configuration, and the managed runtime at any time. Removing the
plugin does not automatically remove user-created reports.

The writing identity can be reviewed or deleted separately. Deleting it only removes
future default preferences; it does not delete user-created drafts or editor data.

Naver editor data can be removed by deleting the dedicated profile, checkpoint,
compatibility-map, and diagnostic paths under `AUTOSEO_DATA_DIR` after signing out
or reviewing any draft state that still matters. Removing them ends local resume
capability and removes the dedicated session; AutoSEO never deletes them implicitly.

The same retention rule applies to the Tistory profile, checkpoints, compatibility
map, diagnostics, and privacy derivatives. Removing Tistory checkpoints also removes
the hosted-media mapping used for duplicate-safe resume.

## Contact

Open a privacy question through the repository's GitHub issue tracker without
including personal data or secrets.
