# Social Image Processor — Current Specification

This document describes the current implemented behavior of Social Image Processor.
For user-facing instructions, see `README.md`. For architectural notes, see
`PROJECT_CONTEXT.md`. For publication handoff details, see `PUBLISHING_WORKFLOW.md`.

## 1. Purpose

Social Image Processor is a Windows desktop tool for preparing edited screenshots and
other images for a social publishing workflow.

The application:

- scans a local source folder;
- lets the user select X and/or Instagram exports per image;
- optionally applies one reusable transparent PNG watermark design;
- exports platform-named JPEG files without cropping or resizing;
- optionally uploads successful exports to Cloudflare R2 through a Worker;
- optionally updates one selected Trello card description with the resulting public URLs.

The downstream Make / Buffer workflow is external to the application.

## 2. Target platform and stack

- Windows 10 / Windows 11
- Python 3.12+
- PySide6
- Pillow
- pytest
- Ruff

The source entry point is:

```powershell
python -m app.main
```

A committed PyInstaller one-folder build path is also available through
`build_windows.ps1` and `social_image_processor.spec`.

## 3. Main workflow

```text
SOURCE
Input folder / Output folder
        ↓
IMAGE PROCESSING
Watermark folder / Design / Size / JPEG quality
        ↓
PUBLISHING
Optional R2 upload / Optional Trello update / Card selection
        ↓
READY TO PROCESS
Loaded / X / Instagram counts
        ↓
IMAGE TABLE + PREVIEW
        ↓
PROCESS IMAGES
        ↓
ACTIVITY + BATCH METRICS
```

Local image processing must remain usable without R2 or Trello.

## 4. Source scanning

Supported source extensions are PNG, JPG, and JPEG.

Scanning is:

- non-recursive;
- case-insensitive by extension;
- asynchronous through the Qt worker pool;
- resilient to invalid or unreadable files.

Source files are never modified.

The image model stores metadata and user selections, not every full-resolution raster.

## 5. Image table and ordering

The table exposes:

- order;
- thumbnail;
- filename;
- dimensions;
- file size;
- X selection;
- Instagram selection;
- watermark availability.

The user can select or clear all X/Instagram choices and move rows up or down.
Visible table order drives platform numbering.

Selections default off.

## 6. Export profiles and naming

Two built-in export platforms are supported:

- X → `X_`
- Instagram → `Insta_`

Both produce JPEG files, preserve source dimensions, and do not crop.

Platform numbering is independent and zero-padded:

```text
X_01.jpg
X_02.jpg
Insta_01.jpg
```

If a generated name already exists, collision suffixes are added:

```text
X_01.jpg
X_01_2.jpg
X_01_3.jpg
```

Output allocation is case-insensitive to match Windows filesystem expectations.

## 7. JPEG processing

JPEG quality defaults to 92 and is configurable from 70 to 100.

PNG transparency is flattened onto the configured background color, which defaults to
black.

Source dimensions and framing are preserved.

The processor does not apply EXIF orientation transforms. EXIF metadata is not copied;
a safe ICC profile may be retained when available.

Final files are written through a same-directory temporary file and atomically finalized.
A source or platform failure must not stop unrelated outputs.

## 8. Watermark system

Watermarks are reusable transparent PNG artwork assets.

The selected watermark folder is scanned non-recursively and valid PNG files are listed
in predictable filename order.

One design is selected globally for the batch and persisted by filename.

Default rendered width is based on 8% of the geometric mean of the source dimensions:

```text
sqrt(width × height) × 0.08
```

The UI allows 3% to 15% in 0.5-point increments. Watermark size is session-only and
returns to 8% on launch.

Rendering rules:

- aspect ratio preserved;
- Lanczos resampling;
- maximum 4× natural asset-width upscale;
- bottom-right placement;
- 1.75% horizontal and vertical margins;
- source image never cropped or resized.

If watermarking is enabled but the selected design is unavailable, processing must fail
validation or skip safely. It must never silently export an unwatermarked replacement.

There is no per-image design override, drag placement, or opacity editor.

## 9. Preview

Selecting a table row renders a scaled preview asynchronously.

The preview:

- preserves aspect ratio;
- displays the dynamic watermark when enabled and available;
- reports missing watermark state;
- is visual confirmation only and does not replace the full-resolution batch path.

## 10. Optional Cloudflare R2 upload

R2 upload is controlled by `Upload exports to R2`.

For each successful local JPEG, `R2UploadService`:

- validates the configured Worker URL;
- builds a deterministic object key;
- performs HTTP `PUT`;
- expects JSON containing a usable `publicUrl`;
- returns an isolated success/failure result.

R2 failures do not invalidate successful local JPEG exports.

If Trello update is enabled, the selected Trello card ID is used as the R2 prefix.
Otherwise the configured remote prefix is used.

## 11. Optional Trello integration

Trello is optional and explicitly configured.

The user can browse:

```text
Board → List → Card
```

The application never guesses the destination card.

On Windows, Trello API credentials are stored in Windows Credential Manager under:

```text
SocialImageProcessor/Trello
```

Credentials are never stored in `settings.json`.

The main Publishing block shows the current Trello connection state and selected card.
The card selector opens the existing Trello configuration dialog and remains clickable
after selection.

Trello update requires R2 upload to be enabled, an active Trello connection, and a
selected card.

## 12. Trello description handoff

When R2 and Trello update are enabled, the batch collects usable public URLs in export
order.

At most one Trello description update is performed per batch.

The application owns exactly one managed section:

```markdown
## URL MAKE
https://example.invalid/X_01.jpg
https://example.invalid/Insta_01.jpg
```

Rules:

- replace only the existing `## URL MAKE` section when present;
- append it when absent;
- preserve text before and after it;
- exclude failed uploads and malformed URLs;
- preserve URL order;
- leave the existing Trello description untouched when no usable URL exists.

The application does not attach image binaries to Trello.

## 13. Settings

Settings are stored as JSON at:

```text
%APPDATA%\SocialImageProcessor\settings.json
```

Persisted non-secret state includes:

- input directory;
- output directory;
- watermark directory;
- JPEG quality;
- watermark enabled state;
- background color;
- selected watermark filename;
- R2 enabled state;
- R2 Worker URL;
- R2 remote prefix;
- Trello update enabled state.

Invalid, missing, stale, or corrupt settings must not prevent application launch.

## 14. UI structure and resize behavior

The main window uses a dark workflow-oriented 2 × 2 dashboard:

```text
SOURCE                  IMAGE PROCESSING
PUBLISHING              READY TO PROCESS
```

Below it, the image table and preview use an approximately even horizontal splitter.
The image region is the primary vertically expanding area.

Activity and Batch Metrics sit in a structural parent container capped at 110 px. The
inner splitter controls only their horizontal division. This avoids native Windows Qt
behavior where a `QSplitter` can lose its own maximum-height constraint when shown.

## 15. Background work and safety

Folder scans, thumbnails, previews, Trello calls, and batch processing use Qt worker
infrastructure so the GUI remains responsive.

Stale asynchronous scan/preview results are ignored through generation tracking.

The application rejects close requests while background work is active.

There is no cancellation mechanism for an active batch.

## 16. Metrics and logging

The UI reports:

- per-export activity;
- R2 upload activity;
- Trello synchronization outcome;
- processing progress;
- source bytes;
- output bytes;
- bytes saved;
- reduction percentage.

Network failures are isolated from local exports.

## 17. Packaging

A one-folder PyInstaller build is supported through:

```powershell
.\build_windows.ps1
```

Expected executable:

```text
dist\SocialImageProcessor\SocialImageProcessor.exe
```

The entire distribution folder must be shipped. There is no installer and no one-file
build requirement. See `PACKAGING.md`.

## 18. Out of scope

The application currently does not provide:

- recursive scanning;
- crop editing;
- automatic Instagram 4:5 conversion;
- image resizing;
- per-image watermark overrides;
- watermark drag placement or opacity editing;
- direct Make API integration;
- direct Buffer API integration;
- direct X or Instagram publishing;
- Trello card creation;
- Trello checklist manipulation;
- installer technology.

## 19. Non-negotiable rules

1. Source files are never modified.
2. No automatic crop.
3. No automatic resize.
4. Local exports remain valid even if optional network integrations fail.
5. Watermarking never silently falls back to unwatermarked output when enabled.
6. Trello destination selection is explicit.
7. Only the managed `## URL MAKE` section may be edited automatically.
8. No telemetry.
9. Local-only processing remains supported.
10. Automated tests must cover functional and UI regressions.

## 20. Validation

Normal development validation:

```powershell
pytest -q
python -m compileall -q app tests
ruff check app tests
ruff format --check app tests
git diff --check
python -m pip check
```

Native Windows validation remains authoritative for platform-specific Qt geometry and
packaged executable behavior.
