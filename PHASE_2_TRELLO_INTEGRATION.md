# Social Image Processor — Phase 2: Trello Integration

## Goal

Extend Social Image Processor with an optional second step that sends processed images directly to a selected Trello card.

The V1 image-processing workflow must remain independent, stable, and fully usable without Trello.

This feature should be developed on a dedicated branch, for example:

```text
feature/phase-2-trello-upload
```

`main` should remain the stable V1 branch until the Trello integration is complete and validated.

---

## Target Workflow

The intended creator workflow is:

```text
Create Trello card
        ↓
Select raw screenshots
        ↓
Photoshop / editing routine
        ↓
Social Image Processor
        ↓
Step 1 — Prepare Images
Resize / watermark / JPEG export / naming
        ↓
Step 2 — Send to Trello
Select card → attach generated images
        ↓
Existing Make automation
        ↓
Cloudflare R2
        ↓
Buffer
        ↓
X / Instagram
```

The application should remain a bridge between local image preparation and the existing Trello-based publishing workflow.

It should **not** become responsible for direct publishing to X, Instagram, Buffer, Cloudflare, or other external services.

---

## Phase 2 — Functional Scope

### 1. Trello Authentication

Add optional Trello authentication.

Requirements:

- Trello integration must remain optional.
- The application must still work fully offline when Trello is not configured.
- Credentials/tokens must never be committed to the repository.
- Credentials should not be stored in plain text inside `settings.json`.
- Prefer secure Windows credential storage when possible.
- Authentication errors must not affect image-processing functionality.

---

### 2. Read Trello Data

Allow the application to retrieve Trello data required to locate the destination card.

Potential UI flow:

```text
Board
  ↓
List
  ↓
Card
```

The user should always explicitly choose the destination card.

The application should **not automatically guess** the target card.

Possible future convenience features:

- remember the last selected board;
- remember the preferred list;
- filter cards by list;
- search cards by name;
- show only active/non-archived cards.

These are optional enhancements and should not be required for the first Trello implementation.

---

### 3. Upload Processed Images

After Step 1 finishes successfully, allow the generated files to be attached directly to the selected Trello card.

The application already generates platform-specific files such as:

```text
Insta_01_example.jpg
Insta_02_example.jpg

X_01_example.jpg
X_02_example.jpg
```

These names should be preserved because the existing Make automation already uses the `Insta_` and `X_` prefixes to route files.

The Trello integration should upload the exported JPEG files exactly as produced by Social Image Processor.

---

## Proposed UI Concept

Keep image processing as **Step 1** and Trello upload as a clearly separated **Step 2**.

Example:

```text
STEP 1 — PREPARE IMAGES

12 source images
7 Instagram exports
5 X exports

[ PROCESS IMAGES ]
```

After successful processing:

```text
STEP 2 — SEND TO TRELLO

Board: Social Networks
List: Ready
Card: Origin Series — 600i

12 files ready

[ ATTACH TO CARD ]
```

The Trello section should only become actionable after valid processed outputs exist.

There should always be an explicit user action before uploading files.

---

## Safety and Reliability

The integration should follow these rules:

- Never upload automatically after image processing.
- Never guess the destination Trello card.
- Always show the selected card before upload.
- Keep Step 1 usable if Trello is unavailable.
- Network failures must not delete or modify local exports.
- Failed uploads should be clearly reported per file.
- Successful and failed attachments should be distinguishable.
- Retrying failed uploads should be possible without reprocessing images.
- Avoid duplicate uploads where practical.

---

## Architecture Direction

Keep Trello-specific logic separate from image-processing logic.

Suggested structure:

```text
app/
├── core/
├── models/
├── services/
│   ├── batch_processor.py
│   ├── folder_scanner.py
│   ├── settings_service.py
│   └── trello_service.py        # future
├── ui/
│   ├── main_window.py
│   ├── preview_panel.py
│   └── trello_panel.py          # future
```

Possible additional models:

```text
TrelloBoard
TrelloList
TrelloCard
TrelloAttachmentResult
TrelloConfiguration
```

The Trello service should expose simple application-level operations rather than spreading API calls through the UI.

Example responsibilities:

```text
list_boards()
list_lists(board_id)
list_cards(list_id)
upload_attachment(card_id, path)
```

The UI should not contain Trello API implementation details.

---

## Testing Strategy

The Trello integration should have its own tests.

Minimum areas:

- authentication/configuration handling;
- board/list/card mapping;
- API response parsing;
- upload success;
- upload failure;
- partial upload failure;
- invalid credentials;
- unavailable network;
- missing local file;
- UI state before and after processing;
- Step 1 remains functional without Trello.

External API calls should be mocked in automated tests.

The existing V1 test suite must continue to pass unchanged unless a deliberate UI contract change requires an update.

---

## Out of Scope for Phase 2

Do not add these features as part of the initial Trello integration:

- direct Instagram publishing;
- direct X publishing;
- Buffer API integration;
- Cloudflare R2 upload;
- Make replacement;
- automatic post scheduling;
- automatic selection of a Trello card;
- Trello card creation from the application;
- Trello description editing;
- automatic checklist manipulation.

These may be considered later, but the first goal is intentionally small:

> Prepare images locally, select the correct Trello card, and attach the generated files.

---

## Definition of Done

Phase 2 can be considered complete when:

1. V1 image processing still works exactly as before.
2. Trello integration is optional.
3. The user can authenticate securely.
4. The application can read boards, lists, and cards.
5. The user can explicitly select a card.
6. Processed images can be uploaded as Trello attachments.
7. Platform filename prefixes are preserved.
8. Upload status and errors are clearly reported.
9. Network/API failures do not affect local exports.
10. Automated tests cover the new integration.
11. The full project test suite passes.

---

## Design Principle

**Step 1 prepares the assets.  
Step 2 hands them to the existing publishing pipeline.**

Social Image Processor should remain focused, predictable, and safe.
