# Project Context

This file is compact architectural memory for future changes.

Current user-facing behavior is documented in `README.md`. The current functional
contract is in `SPEC.md`. Publication handoff details are in `PUBLISHING_WORKFLOW.md`,
and Windows packaging is documented in `PACKAGING.md`.

## Current state

Social Image Processor is a Windows PySide6 desktop application that prepares local
JPEG exports for X and Instagram and can optionally hand those exports into the
publishing pipeline through Cloudflare R2 and Trello.

Current package version remains `0.1.0` in `app/__init__.py`.

The main workflow is:

```text
Source
  ↓
Image Processing
  ↓
Publishing
  ↓
Ready to Process
  ↓
Image Table + Preview
  ↓
Local JPEG exports
  ↓
Optional R2 upload
  ↓
Optional Trello ## URL MAKE update
  ↓
External Make / Buffer workflow
```

The old direct-Trello-attachment design has been removed. There is no user-facing
`ATTACH TO CARD` workflow.

## Architecture and invariants

Dependency direction is broadly:

```text
UI → services → models/core
```

`app/core` is Qt-independent and uses Pillow. Services are synchronous and testable;
Qt workers adapt them to the GUI.

Never retain all full-resolution sources in UI models and never move Pillow image
processing into widgets.

### Source scanning

- non-recursive;
- PNG/JPG/JPEG, case-insensitive;
- raw stored dimensions;
- source files never modified;
- asynchronous scan/thumbnail/preview work;
- stale async results ignored through generation tracking.

### Exports

- X prefix: `X_`;
- Instagram prefix: `Insta_`;
- independent sequence numbering by visible table order;
- JPEG output;
- no crop;
- no resize;
- JPEG quality default 92, UI range 70–100;
- transparency flattened to configured background, default black;
- collision-safe, case-insensitive output allocation;
- atomic finalization through same-directory temporary files.

### Dynamic watermark

Watermarks are reusable transparent PNG artwork assets selected globally by filename.

Geometry is deterministic:

- default width reference: 8% of `sqrt(source_width × source_height)`;
- UI range: 3%–15% in 0.5-point steps;
- maximum upscale: 4× natural asset width;
- Lanczos resampling;
- bottom-right placement;
- 1.75% margin on each source axis.

Watermark size is intentionally session-only and resets to 8% on launch.

If watermarking is enabled without a usable selected design, processing must not
silently export an unwatermarked result.

### Batch behavior

Batch failures are isolated by source/platform. A failed local export, R2 upload, or
Trello update must not invalidate unrelated successful local outputs.

Batch metrics count each successful source once and each successful output file.
Signed savings may be negative.

There is no batch cancellation. Closing is rejected while workers are active.

## Optional R2 integration

`R2UploadService` owns transport behavior.

For each successful local export it can:

- validate the Worker URL;
- generate a deterministic object key;
- perform HTTP `PUT`;
- parse JSON `publicUrl`;
- return an isolated upload result.

When Trello update is enabled, the selected card ID becomes the R2 prefix. Otherwise
the configured remote prefix is used.

R2 is optional and local processing remains valid without it.

## Optional Trello integration

Trello credentials never enter application settings.

On Windows they are stored in Credential Manager as:

```text
SocialImageProcessor/Trello
```

Trello navigation is explicit:

```text
Board → List → Card
```

The application never guesses a card.

`TrelloService` supports board/list/card browsing plus card-description read/update.
It does not own image processing and no longer uploads JPEG attachments.

Trello update requires:

- R2 upload enabled;
- Trello connected;
- selected card.

## `## URL MAKE` contract

The downstream text handoff is one application-owned Markdown section in the selected
Trello card description:

```markdown
## URL MAKE
https://...
```

`replace_url_make_section()` must:

- replace only that section when present;
- append it when absent;
- preserve unrelated description content;
- preserve URL order.

The batch processor must not update Trello when there are no usable public URLs, so an
existing section is preserved after complete upload failure.

At most one Trello description update is performed per batch.

## UI structure

The current main window is organized as:

```text
SOURCE                  IMAGE PROCESSING
PUBLISHING              READY TO PROCESS

IMAGE TABLE             PREVIEW

ACTIVITY                BATCH METRICS

PROGRESS
```

The table/preview splitter targets an approximately even horizontal allocation at large
window sizes.

The image region is the primary vertically expanding area.

Activity / Batch Metrics are wrapped in `results_container`, capped at 110 px. Do not
move the height constraint back onto `QSplitter`: native Windows/PySide6 testing showed
that the splitter can lose its maximum-height constraint on show/resize.

## Settings

Settings are JSON at:

```text
%APPDATA%\SocialImageProcessor\settings.json
```

They contain non-secret preferences only. Missing, corrupt, incomplete, stale, and
invalid values recover safely.

Persisted settings include folder paths, JPEG quality, watermark state/selection, R2
configuration and publishing toggles. Trello secrets stay in Windows Credential Manager.

Restored folder scans are deferred until the Qt event loop.

## Packaging boundary

The source entry point is:

```powershell
python -m app.main
```

The repository also contains a supported one-folder PyInstaller build:

```powershell
.\build_windows.ps1
```

using `social_image_processor.spec` and PyInstaller 6.15.0 from
`requirements-dev.txt`.

Expected artifact:

```text
dist\SocialImageProcessor\SocialImageProcessor.exe
```

There is no installer and no one-file packaging contract. See `PACKAGING.md`.

## Deferred / out-of-scope features

Do not add without an explicit task:

- recursive scanning;
- crop editor or automatic Instagram 4:5 conversion;
- image resizing;
- per-image watermark overrides;
- watermark drag placement / opacity editor;
- metadata-policy UI;
- direct Make API calls;
- direct Buffer API calls;
- direct social-network publishing;
- Trello card creation;
- Trello checklist manipulation;
- installer technology.

## Validation expectation

Run the complete test suite after functional changes. Native Windows tests are especially
important for startup/relaunch, native dialogs, restored paths, Qt geometry, preview
layout, and packaging behavior.
