# Social Image Processor

Social Image Processor is an offline Windows desktop application for turning PNG,
JPG, and JPEG source images into platform-named JPEG exports. It is intended for
photographers and creators who want predictable full-frame watermarking and smaller
files without modifying their originals.

**V1 version:** `0.1.0`

## Optional Trello browsing (Milestone 1)

The separate Trello panel can connect and browse open **Board → List → Card**
destinations. Choices are dependent and the application never selects a destination
card automatically. This milestone is read-only: it does not create cards, alter
checklists, or upload attachments. Trello errors remain in the Trello panel and do
not disable local image processing.

On Windows, the API key and user token are stored as one generic credential in
Windows Credential Manager under `SocialImageProcessor/Trello`. They are never
written to `settings.json`. The implementation uses Windows' built-in credential
API and Python's standard HTTP library, so adding `keyring` or another runtime
dependency was not justified for this Windows-targeted application. Source builds
on other operating systems retain the disconnected/offline state but cannot save
Trello credentials.

## V1 features

- Non-recursive, case-insensitive scanning of PNG, JPG, and JPEG files.
- Asynchronous thumbnails, previews, scans, and batch processing in a PySide6 UI.
- Independent X and Instagram choices per image, including dual export.
- JPEG quality from 70 to 100 (default 92), original pixel dimensions, no crop,
  and no resize.
- Strict exact-resolution, full-frame PNG watermark matching and preview.
- Safe skip when a required watermark is missing or ambiguous.
- Collision-safe numbered names and atomic output finalization.
- Per-file errors, progress, logs, and signed size/reduction statistics.
- Local settings restoration and robust handling of stale paths and corrupt files.

X outputs use `X_` and Instagram outputs use `Insta_`. For example, selecting both
platforms for `photo.png` creates `X_photo.jpg` and `Insta_photo.jpg`. Existing
names are preserved; later files become `X_photo_2.jpg`, `X_photo_3.jpg`, and so on.
Both profiles preserve the source framing and dimensions in V1.

## Requirements

- Windows 10 or Windows 11.
- Python 3.12 or newer for source-based use.
- PySide6 and Pillow at runtime.
- pytest and Ruff for development checks.

Dependency versions are declared in [`requirements.txt`](requirements.txt) with
compatible ranges suitable for V1. Packaging tools are deliberately not runtime
dependencies.

## Install from source

In PowerShell, from a repository checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell execution policy prevents activation, use Command Prompt and run
`.venv\Scripts\activate.bat`, or invoke `.venv\Scripts\python.exe` directly.

## Launch

Run from the repository root:

```powershell
python -m app.main
```

Choose distinct input and output folders, optionally choose a watermark folder,
select X and/or Instagram for each desired source, and click **PROCESS IMAGES**.
Folder settings, JPEG quality, watermark state, and background color are restored
on later launches.

## Exact-resolution watermark workflow

A V1 watermark is a transparent, **full-frame PNG**, not a logo that the application
positions. Prepare it at precisely the source resolution with the logo already in
its final location. A `3440 × 1440` source therefore needs one unique `3440 × 1440`
watermark canvas. Matching uses actual pixel dimensions, not filenames.

The overlay is composited one-to-one at `(0, 0)`. V1 never scales, moves, crops, or
selects by aspect ratio. With **Apply watermark** enabled:

- exactly one dimensional match: export with that watermark;
- no match: skip the complete source;
- multiple matches: report ambiguity and skip the complete source.

Disable watermarking explicitly to make unwatermarked exports. Transparent source
pixels are flattened onto black by default before JPEG encoding.

## Settings, offline operation, and privacy

On Windows settings live at:

```text
%APPDATA%\SocialImageProcessor\settings.json
```

They do not live beside a future executable. The JSON file contains folder paths
and non-secret preferences only. Missing, incomplete, stale, inaccessible, or
corrupt settings recover safely.

Image processing works fully offline. The optional Trello panel makes network
requests only after **Connect Trello** is clicked. There is no telemetry, Make,
Buffer, or direct social-publishing integration.

## Architecture

```text
app/main.py                 application entry point
app/ui/                     Qt widgets and background-worker adapters
app/services/               scanning, settings, and batch orchestration
app/core/                   Qt-independent Pillow processing and naming
app/models/                 immutable settings, image, watermark, and result models
app/utils/                  presentation formatting helpers
tests/                      generated-file unit, integration, and offscreen UI tests
```

Dependency direction is UI → services → models/core. Core processing has no Qt
dependency; services remain synchronously testable; full-resolution images are
opened and released progressively. Runtime settings and image paths are supplied
by the user or OS, so operation does not depend on the repository working directory.

## Validation

```powershell
pytest -q
python -m compileall -q app tests
ruff check app tests
ruff format --check app tests
git diff --check
python -m pip check
```

For headless/offscreen Qt validation in PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest -q tests/test_ui.py
```

The native Windows workflow has also been manually validated for startup/relaunch,
Browse scanning, restored settings, thumbnails, previews, watermark safety, both
platform profiles, PNG-to-JPEG processing, and repeated runs.

## Current limitations

V1 intentionally has no recursion, cancellation, drag and drop, crop editor,
automatic Instagram 4:5 conversion, resizing, watermark scaling fallback,
per-image watermark overrides, metadata-policy UI, direct publishing, Trello
attachment upload, or remote content mutation. It preserves raw stored dimensions
but does not guarantee
metadata identity or apply EXIF orientation transformations. A close request is
rejected while background work is active; wait for it to finish.

## Future Windows packaging

A standalone executable is planned but is **not built in this phase**. The source
entry point is packaging-safe and settings remain in `%APPDATA%`. See
[`PACKAGING.md`](PACKAGING.md) for the recommended dedicated PyInstaller task,
asset considerations, and validation checklist. No installer technology is part of
V1 hardening.

## License

Licensed under the GNU General Public License v3.0; see [`LICENSE`](LICENSE).
