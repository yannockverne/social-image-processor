# Social Image Processor — Publishing Workflow

This document describes the current optional publication handoff implemented by Social Image Processor.

The original Phase 2 concept used direct Trello JPEG attachments. That design was superseded during implementation by a lighter URL-based workflow.

Current handoff:

```text
Local JPEG export
        ↓
Optional Cloudflare R2 upload
        ↓
Worker publicUrl
        ↓
Optional Trello card-description update
        ↓
## URL MAKE
        ↓
External Make automation
        ↓
Buffer
        ↓
X / Instagram
```

Social Image Processor does **not** publish directly to X, Instagram, Buffer, or Make.

## 1. Local export remains authoritative

The application always treats local JPEG creation as the primary result.

Network integrations are optional and failure-isolated:

- an R2 failure does not invalidate a successful local JPEG;
- a Trello failure does not invalidate local JPEGs or successful R2 uploads;
- local-only processing remains supported.

## 2. Cloudflare R2 upload

R2 upload is controlled by:

```text
Upload exports to R2
```

For every successful finalized JPEG, `R2UploadService`:

1. validates the Worker URL;
2. generates a deterministic object key;
3. uploads through HTTP `PUT`;
4. expects JSON containing `publicUrl`;
5. returns an isolated success/failure result.

Only successful local exports are uploaded.

If Trello update is enabled, the selected Trello card ID is used as the object-prefix namespace. Otherwise the configured R2 remote prefix is used.

Malformed or missing public URLs are not forwarded to Trello.

## 3. Trello authentication and browsing

Trello integration remains optional.

Navigation is explicit:

```text
Board → List → Card
```

The application never guesses a destination card.

On Windows, the Trello API key and token are stored in Windows Credential Manager under:

```text
SocialImageProcessor/Trello
```

Credentials are never written to `settings.json`.

The main Publishing block shows Trello connection state and the currently selected card.

When no card is selected, the selector displays:

```text
No card selected — Select card
```

The same control remains clickable after selection so the destination can be changed.

## 4. Trello update prerequisites

`Update Trello card` is dependent on the existing publishing state.

Before processing with Trello updates enabled, the application requires:

- R2 upload enabled;
- a valid R2 Worker URL;
- an active Trello connection;
- an explicitly selected Trello card.

These validation rules do not apply to local-only processing.

## 5. `## URL MAKE` contract

The application owns one managed Markdown section in the selected Trello card description:

```markdown
## URL MAKE
https://example.invalid/X_01.jpg
https://example.invalid/Insta_01.jpg
```

The URLs are usable public R2 URLs from the current batch and preserve export order.

Update rules are deliberately narrow:

- if the section exists, replace only that section;
- if it does not exist, append it cleanly;
- preserve text before and after the section;
- preserve URL order;
- exclude failed uploads;
- exclude malformed/missing URLs;
- if no usable URL exists, leave the Trello description untouched.

An existing `## URL MAKE` section must therefore never be erased merely because the current batch produced no usable upload URL.

## 6. One Trello update per batch

The batch processor collects usable upload URLs while processing exports.

After the batch finishes, and only when all prerequisites are satisfied, it:

1. reads the current Trello card description;
2. updates the managed `## URL MAKE` section;
3. writes the description once.

There is at most one Trello description update per batch, not one API call per exported file.

## 7. Current UI integration

The old two-step `PROCESS IMAGES` → `ATTACH TO CARD` workflow has been removed.

The current main window is organized around the real workflow:

```text
SOURCE                  IMAGE PROCESSING
PUBLISHING              READY TO PROCESS

IMAGE TABLE             PREVIEW

ACTIVITY                BATCH METRICS
```

The Publishing block contains:

- `Upload exports to R2`;
- `Update Trello card`;
- R2 status;
- Trello connection status;
- Trello card selector.

The Ready to Process block contains:

- loaded-image count;
- X-selection count;
- Instagram-selection count;
- the single `PROCESS IMAGES` action.

## 8. Service responsibilities

### `R2UploadService`

- validate Worker URL;
- build deterministic object keys;
- upload finalized JPEG files;
- parse/validate `publicUrl`.

### `TrelloService`

- list boards;
- list lists;
- list cards;
- read card description;
- update card description.

### `url_make`

- create or replace exactly one managed `## URL MAKE` section;
- preserve unrelated card-description content.

### `BatchProcessor`

- orchestrate local exports;
- optionally invoke R2 upload;
- collect usable URLs;
- perform at most one final Trello description update.

The UI does not contain transport-specific R2/Trello implementation logic.

## 9. Failure isolation

The integration contract is:

- local export success is never revoked by network failure;
- failed R2 uploads are reported per output;
- malformed Worker responses are treated as upload failures;
- failed/malformed URLs are excluded from Trello synchronization;
- Trello update failure is logged separately;
- existing Trello content is preserved when no usable URL exists.

## 10. Superseded design

The following ideas existed in the original Phase 2 plan and are intentionally no longer part of the application:

- direct JPEG attachment upload to Trello;
- `ATTACH TO CARD` button;
- separate post-processing Step 2 upload UI;
- Trello attachment-result workflow;
- Make consuming binary Trello attachments;
- treating Cloudflare R2 as out of scope.

They were replaced by:

```text
local export → R2 → public URL → Trello description → Make / Buffer
```

## 11. Still out of scope

Social Image Processor does not currently provide:

- direct Instagram publishing;
- direct X publishing;
- direct Buffer API integration;
- direct Make API integration;
- automatic social scheduling;
- Trello card creation;
- automatic Trello card selection;
- arbitrary Trello description editing outside `## URL MAKE`;
- Trello checklist manipulation.

## 12. Design principle

> **Prepare images locally, upload successful exports once, and hand the downstream publishing pipeline stable public URLs rather than binary Trello attachments.**
