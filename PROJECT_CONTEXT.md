# Project Context

`SPEC.md` is the V1 functional source of truth. This file is compact cross-task
architectural memory.

## Current state

Phases 1–6 are implemented. Phase 6 hardens the final V1 source release and prepares
a separate PyInstaller task; it does not build an executable. V1 is version `0.1.0`
in `app/__init__.py`.

Real Windows validation has covered startup/relaunch, Browse, restored settings,
scanning/thumbnails/previews, exact/missing watermark behavior, X/Instagram/dual
exports, PNG-to-JPEG batches, repeated runs, and the Windows test suite.

Phase 2 Trello Milestone 1 adds an optional, read-only Board → List → Card browser.
Trello models, HTTP operations, Windows Credential Manager access, and UI live in
separate modules. No attachment upload or other remote mutation is implemented.

## Architecture and invariants

Dependency direction is UI → services → models/core. `app/core` is Qt-independent
and uses Pillow. Services are synchronous/testable; Qt workers adapt them for the
UI. Never retain all full-resolution sources or put Pillow processing in widgets.

Scanning is non-recursive, case-insensitive for PNG/JPG/JPEG, filename-sorted, and
uses raw stored dimensions without EXIF orientation transforms. Source files are
never modified.

X uses `X_`; Instagram uses `Insta_`. Both output JPEG, preserve dimensions, and do
not crop or resize. Per-image selections default off.

Watermarks are transparent full-canvas PNGs matched by exact pixel dimensions.
Composite one-to-one at `(0, 0)` with no scaling, positioning, ratio fallback, or
crop. Missing and duplicate-dimension matches skip the whole selected source when
watermarking is enabled.

JPEG quality defaults to 92 (UI range 70–100); transparency defaults to black.
Metadata identity is not guaranteed; ICC may be retained when safe. Existing and
batch-reserved output names are compared case-insensitively and numbered. Writes
use a same-directory temporary JPEG, writable-descriptor `fsync`, exclusive final
reservation, atomic replace, and failure cleanup.

Batch failures are isolated by source and platform. Count each successful source
once and every successful output; signed savings may be negative. No cancellation.

Settings are JSON at `%APPDATA%/SocialImageProcessor/settings.json` on Windows and
recover from missing, corrupt, incomplete, or invalid values. Restored scans are
deferred until the Qt event loop. Browse schedules one scan, cancellation schedules
none, workers/signal bridges remain retained, stale async scan/preview results are
ignored, and close is rejected during background work.

Trello API credentials never enter application settings. On Windows they are held
as a generic Credential Manager entry named `SocialImageProcessor/Trello`. Trello
HTTP calls use the existing worker pool, are initiated only by the optional panel,
and cannot gate or disable local batch processing.

## Packaging boundary

`python -m app.main` is the entry point and imports have no launch side effect.
Runtime behavior does not depend on repository-relative paths. PyInstaller stays a
separate build dependency; see `PACKAGING.md`. There are currently no runtime assets
or icon and no installer technology.

## Deferred features

Do not add drag/drop, crop or 4:5 conversion, resizing, watermark fallback/override,
preset/plugin frameworks, metadata policy UI, Trello attachment upload, direct
Make/Buffer/social publishing, installer technology, or an actual executable
without a separately approved task.
