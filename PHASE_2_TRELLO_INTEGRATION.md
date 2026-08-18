# Social Image Processor — Phase 2: Trello Integration

## Status

Phase 2 is implemented, but the final workflow evolved substantially from the original plan documented here.

The initial concept was to attach generated JPEG files directly to a selected Trello card and let the existing Make automation move those attachments through the publishing pipeline.

That design was replaced during implementation.

The current application instead:

1. prepares local JPEG exports;
2. optionally uploads successful exports directly to Cloudflare R2 through a configured Worker;
3. collects the returned public URLs;
4. optionally updates the selected Trello card description once per batch;
5. manages an application-owned `## URL MAKE` section containing those URLs;
6. leaves the downstream Make / Buffer workflow to consume that text-based handoff.

Trello attachments are no longer part of the user-facing workflow.

---

## Current Workflow

```text
Create / choose Trello card
        ↓
Select raw screenshots
        ↓
Photoshop / editing routine
        ↓
Social Image Processor
        ↓
Local image preparation
JPEG export / naming / optional watermark
        ↓
Optional direct R2 upload
Cloudflare Worker → publicUrl
        ↓
Optional Trello card-description update
## URL MAKE
        ↓
Existing Make automation
        ↓
Buffer
        ↓
X / Instagram
```

The application remains a bridge between local image preparation and the external publishing workflow.

It does **not** publish directly to X, Instagram, Buffer, or Make.

---

## Implemented Functional Scope

### 1. Optional Trello authentication

Trello integration remains optional.

The application can be used for local image processing without Trello.

On Windows, the Trello API key and token are stored in Windows Credential Manager under:

```text
SocialImageProcessor/Trello
```

Credentials are not written to `settings.json` and are never committed to the repository.

Authentication and network failures do not invalidate successful local exports.

---

### 2. Board → List → Card browsing

The application can retrieve open Trello boards, lists, and cards through the Trello API.

The navigation flow remains explicit:

```text
Board
  ↓
List
  ↓
Card
```

The application never guesses the destination card automatically.

The selected card is shown directly in the main **Publishing** block.

If no card is selected, the main-window selector displays:

```text
No card selected — Select card
```

Clicking the selector opens the existing Trello configuration flow.

When a card is selected, the same control displays the card name and remains clickable to change the destination.

---

### 3. Direct Cloudflare R2 upload

The original direct-Trello-attachment design was replaced by direct R2 upload.

When **Upload exports to R2** is enabled, each successful finalized JPEG is uploaded through the configured Cloudflare Worker using HTTP `PUT`.

The Worker must return JSON containing a usable:

```text
publicUrl
```

Only successful local exports are uploaded.

An R2 failure is isolated to that output and does not invalidate:

- the local JPEG;
- other local exports;
- other successful uploads.

Object keys are deterministic and based on the generated export filename.

---

### 4. Trello description synchronization

When **Update Trello card** is enabled and a card is selected, the application may update that card after the batch.

The application does not upload JPEG attachments to Trello.

Instead, it reads the existing card description, updates one managed Markdown section, and writes the resulting description back to Trello.

The managed section is:

```markdown
## URL MAKE
https://example.invalid/X_01_photo.jpg
https://example.invalid/Insta_01_photo.jpg
```

The URLs are the usable public R2 URLs produced by the current batch and preserve export order.

The application performs at most one Trello description update per batch.

---

## `## URL MAKE` contract

The `## URL MAKE` block is owned by Social Image Processor.

Its update rules are deliberately narrow:

- if the section already exists, only that section is replaced;
- text before and after the section is preserved;
- if the section does not exist, it is appended cleanly;
- URL order is preserved;
- failed uploads and malformed URLs are excluded;
- if no usable URL exists, the Trello description is left untouched;
- an existing `## URL MAKE` section is therefore never erased merely because the current batch produced no usable URL.

This block is the text handoff consumed by the downstream Make / Buffer workflow.

---

## Main UI integration

The original separate **Step 1 / Step 2 / ATTACH TO CARD** concept was removed.

The current main window is organized around the actual workflow:

```text
SOURCE                  IMAGE PROCESSING
PUBLISHING              READY TO PROCESS

IMAGE TABLE             PREVIEW

ACTIVITY                BATCH METRICS
```

The **Publishing** block contains:

- `Upload exports to R2`;
- `Update Trello card`;
- R2 status;
- Trello connection status;
- the selected Trello card control.

The **Ready to Process** block contains:

- loaded image count;
- X selection count;
- Instagram selection count;
- the single `PROCESS IMAGES` action.

Trello card selection remains visible but is disabled when Trello updating is not active according to the existing R2/Trello dependency rules.

---

## Failure isolation and safety

The implemented workflow follows these rules:

- local export remains authoritative;
- R2 is optional;
- Trello is optional;
- no Trello card is selected automatically;
- local exports are not deleted or invalidated by network failures;
- R2 failures are recorded per output;
- malformed or missing R2 public URLs are ignored for Trello synchronization;
- Trello failures are recorded without invalidating local exports or successful R2 uploads;
- Trello receives one description update per batch, not one API call per exported image;
- when no usable URL exists, an existing managed section is preserved.

---

## Architecture

Trello and R2 integration remain separated from core image processing.

Relevant structure:

```text
app/
├── core/
│   ├── image_processing.py
│   ├── output_naming.py
│   └── watermarking.py
├── models/
│   ├── trello.py
│   ├── results.py
│   └── settings.py
├── services/
│   ├── batch_processor.py
│   ├── r2_upload_service.py
│   ├── settings_service.py
│   ├── trello_service.py
│   └── url_make.py
└── ui/
    ├── main_window.py
    ├── integration_dialogs.py
    └── trello_panel.py
```

Responsibilities are intentionally separated:

### `TrelloService`

- load boards;
- load lists;
- load cards;
- read a card description;
- update a card description.

### `R2UploadService`

- validate the Worker URL;
- generate deterministic object keys;
- upload generated JPEG files;
- parse and validate returned public URLs.

### `url_make`

- create or replace only the application-owned `## URL MAKE` section;
- preserve unrelated card-description content.

### `BatchProcessor`

- orchestrate local exports;
- optionally invoke R2 uploads;
- collect usable public URLs;
- perform at most one final Trello description update.

The UI does not contain transport-specific Trello or R2 implementation details.

---

## Testing strategy

The integration is covered by focused automated tests for:

- Trello authentication/configuration behavior;
- board/list/card mapping;
- Trello card-description read/update operations;
- R2 upload success and failure;
- Worker URL validation;
- malformed or missing `publicUrl` responses;
- partial and complete R2 failures;
- URL ordering;
- managed-section creation and replacement;
- preservation of an existing section when no usable URL exists;
- one Trello update per batch;
- Trello failure isolation;
- settings backward compatibility;
- main-window integration state and Trello card selector behavior.

External network operations are mocked in automated tests.

Native Windows UI validation remains useful in addition to automated tests because Qt geometry and platform behavior can differ from the headless development container.

---

## Removed / superseded Phase 2 ideas

The following items were part of the original Phase 2 plan but are **not** part of the current implementation:

- direct attachment of generated JPEG files to Trello cards;
- an `ATTACH TO CARD` action;
- explicit post-processing Step 2 upload UI;
- retrying individual Trello attachments;
- Trello attachment-result models as the primary handoff;
- Make receiving binary image attachments from Trello;
- Cloudflare R2 being out of scope.

These were superseded by the more direct and lightweight:

```text
local export → R2 → public URL → Trello description → Make / Buffer
```

workflow.

---

## Still out of scope

The application still does not provide:

- direct Instagram publishing;
- direct X publishing;
- direct Buffer API integration;
- direct Make API integration;
- automatic social scheduling;
- automatic Trello card creation;
- automatic card selection;
- arbitrary Trello description editing outside the managed section;
- checklist manipulation.

---

## Definition of Done — implemented state

Phase 2 is considered complete in its evolved form because:

1. Local image processing remains independently usable.
2. Trello integration is optional.
3. Trello credentials are stored securely on Windows.
4. Boards, lists, and cards can be browsed explicitly.
5. The selected Trello card is visible and changeable from the main workflow.
6. Successful local exports can optionally upload directly to R2.
7. Public R2 URLs are validated before use.
8. The selected Trello card can receive one managed description update per batch.
9. The `## URL MAKE` section preserves unrelated card content.
10. Network failures do not invalidate successful local exports.
11. Automated tests cover the integration paths and failure isolation.
12. The full application remains compatible with a local-only workflow.

---

## Design Principle

The original principle remains valid, but the handoff mechanism changed:

> **Prepare images locally, upload successful exports once, and hand the publishing pipeline stable public URLs instead of binary Trello attachments.**

Social Image Processor remains focused on predictable asset preparation and a controlled handoff to the existing publication workflow.
