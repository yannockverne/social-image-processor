# Social Image Processor

Social Image Processor is a Windows desktop application for preparing image batches for social publishing.
It turns PNG, JPG, and JPEG source images into platform-named JPEG exports, optionally applies a reusable watermark, can upload successful exports directly to Cloudflare R2 through a Worker, and can update a selected Trello card with the resulting public URLs.

The application is designed around a simple workflow:

**Source → Image Processing → Publishing → Ready to Process → Selection / Preview → Activity / Results**

It preserves the source framing and pixel dimensions: there is no automatic crop or resize.

## Current features

- Non-recursive, case-insensitive scanning of PNG, JPG, and JPEG files.
- Asynchronous folder scans, thumbnails, previews, and batch processing in a PySide6 desktop UI.
- Workflow-oriented 2 × 2 dashboard for Source, Image Processing, Publishing, and Ready to Process.
- Independent X and Instagram selection per image, including dual export.
- Visible image ordering with Move Up / Move Down controls; table order drives processing and platform numbering.
- JPEG quality from 70 to 100, defaulting to 92.
- Original pixel dimensions preserved; no crop and no resize.
- Dynamic reusable PNG watermark design with live preview and proportional sizing.
- Watermark size adjustable from 3% to 15% in 0.5-point steps; default 8% per launch.
- Safe handling of missing or invalid watermark selections.
- Collision-safe numbered export names and atomic output finalization.
- Optional direct upload of successful JPEG exports to Cloudflare R2 through a configured Worker.
- Optional Trello integration with Board → List → Card browsing and Windows Credential Manager storage.
- Selected Trello card displayed directly in the main Publishing block and reusable as a quick selector.
- Optional Trello card-description synchronization using an application-owned `## URL MAKE` section.
- Per-file export/upload errors without invalidating successful local outputs.
- Progress, activity logging, and batch metrics for source size, output size, saved bytes, and reduction.
- Local settings restoration with robust handling of stale paths and corrupt files.

## Documentation

- [`SPEC.md`](SPEC.md) — current functional contract.
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — compact architectural memory and invariants.
- [`PUBLISHING_WORKFLOW.md`](PUBLISHING_WORKFLOW.md) — R2 → Trello → Make / Buffer handoff.
- [`PACKAGING.md`](PACKAGING.md) — supported Windows one-folder PyInstaller build and validation.

## Export naming

X outputs use `X_` and Instagram outputs use `Insta_`.

Platform selections are numbered independently in visible table order. For example, one batch can produce:

```text
X_01.jpg
Insta_01.jpg
```

Existing generated names are collision-safe; suffixes such as `_2`, `_3`, and so on are added when needed.

## Requirements

- Windows 10 or Windows 11.
- Python 3.12 or newer for source-based use.
- PySide6 and Pillow at runtime.
- pytest and Ruff for development checks.

Dependency versions are declared in [`requirements.txt`](requirements.txt).

## Install from source

In PowerShell, from a repository checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell execution policy prevents activation, use Command Prompt and run:

```text
.venv\Scripts\activate.bat
```

or invoke `.venv\Scripts\python.exe` directly.

## Launch

Run from the repository root:

```powershell
python -m app.main
```

Typical use:

1. Choose the input and output folders.
2. Optionally choose a watermark folder and design.
3. Select X and/or Instagram for each source image.
4. Optionally enable R2 upload.
5. Optionally enable Trello update and select a card.
6. Review the preview and Ready to Process summary.
7. Click **PROCESS IMAGES**.

Folder settings, JPEG quality, watermark state, selected watermark, and publishing preferences are restored on later launches where applicable. Watermark size is intentionally session-only and returns to 8% on each launch.

## Dynamic watermark workflow

Put reusable transparent PNG artwork in the selected watermark folder. Valid immediate `.png` files appear alphabetically in the **Design** selector; other formats, directories, and corrupt images are ignored safely.

Artwork width defaults to **8% of the geometric mean of the source dimensions** (`sqrt(width × height)`), preserving aspect ratio with Lanczos resampling and a 4× natural-size upscale cap.

The **Watermark size** control can adjust this from 3% to 15% in 0.5-point steps for the current session. The watermark is placed bottom-right with **1.75%** horizontal and vertical margins relative to the corresponding source dimension. The entire mark remains inside the image and the source is never cropped or resized.

Use tightly trimmed transparent assets with enough source resolution for the largest intended output.

The current implementation uses one watermark design for the whole batch and has no drag placement, opacity editor, or per-image watermark override. If watermarking is enabled without a usable design selection, processing does not silently export an unwatermarked replacement.

## Cloudflare R2 upload

R2 upload is optional and controlled by **Upload exports to R2**.

The application sends each successful finalized JPEG to a configured Cloudflare Worker using HTTP `PUT`. The Worker is expected to return JSON containing a usable `publicUrl`.

Uploads happen only after a local export succeeds. An R2 failure is recorded for that output but does not invalidate the local JPEG or other successful files in the batch.

The Worker URL and optional remote prefix are configured through the R2 settings UI. Object keys are deterministic and based on the generated export filename.

## Trello integration

Trello integration is optional.

The application can connect to Trello and browse open:

**Board → List → Card**

The main Publishing section shows the selected card. If no card is selected, the selector button opens the existing Trello configuration flow. When a card is selected, the same button displays its name and remains clickable to change the destination.

On Windows, the Trello API key and token are stored together in Windows Credential Manager under:

```text
SocialImageProcessor/Trello
```

Credentials are never written to `settings.json`.

The Trello service can read and update the selected card description. The application does not create cards or modify unrelated card fields.

## `## URL MAKE` managed section

When both R2 upload and Trello update are enabled, usable public R2 URLs are collected in export order after processing.

If at least one usable URL exists, the application performs a single Trello description update for the batch and manages exactly one section:

```markdown
## URL MAKE
https://example.invalid/X_01.jpg
https://example.invalid/Insta_01.jpg
```

If the section already exists, only that managed section is replaced. Text before and after it is preserved. If the section does not exist, it is appended cleanly.

If no usable upload URLs are produced, the existing Trello description and any previous `## URL MAKE` section are left untouched.

This section is intended to feed the external Make / Buffer publication workflow. Social Image Processor itself does **not** call Make, Buffer, X, or Instagram APIs directly.

## Settings, network use, and privacy

On Windows settings live at:

```text
%APPDATA%\SocialImageProcessor\settings.json
```

The JSON file contains folder paths and non-secret preferences only. Missing, incomplete, stale, inaccessible, or corrupt settings recover safely.

Local image processing works without network access.

Network requests occur only when the corresponding optional integration is used:

- R2 upload communicates with the configured Cloudflare Worker.
- Trello browsing and description updates communicate with Trello.

There is no telemetry and no direct social-network publishing API in the application.

## Architecture

```text
app/main.py                 application entry point
app/ui/                     Qt widgets, dialogs, and worker adapters
app/services/               scanning, settings, batch orchestration, R2, Trello
app/core/                   Qt-independent Pillow processing and naming
app/models/                 immutable settings, image, watermark, and result models
app/utils/                  presentation formatting helpers
tests/                      unit, integration, and UI tests
```

Dependency direction remains centered around UI → services → models/core. Core processing has no Qt dependency, and services are designed to remain synchronously testable.

Full-resolution images are opened and released progressively. Runtime settings and image paths are supplied by the user or OS, so normal operation does not depend on the repository working directory.

## Validation

Typical development checks:

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

Native Windows testing is still important for UI geometry, startup/relaunch behavior, restored paths, thumbnails, previews, watermark rendering, and integration-state behavior.

## Current limitations

The application currently has no:

- recursive folder scanning
- cancellation during active background work
- crop editor
- automatic Instagram 4:5 conversion
- image resize workflow
- per-image watermark override
- watermark drag placement or opacity editor
- Trello card creation
- direct Make or Buffer API calls
- direct X or Instagram publishing
- installer

It preserves stored source dimensions but does not promise metadata identity or provide a metadata-policy UI. A close request is rejected while background work is active; wait for the current work to finish.

## Windows packaging

The repository contains a supported one-folder PyInstaller build path:

```powershell
python -m pip install -r requirements-dev.txt
.\build_windows.ps1
```

Expected executable:

```text
dist\SocialImageProcessor\SocialImageProcessor.exe
```

Ship the complete `dist\SocialImageProcessor\` folder. There is currently no installer or one-file distribution contract. See [`PACKAGING.md`](PACKAGING.md) for build details and the native Windows validation checklist.

## License

Licensed under the GNU General Public License v3.0; see [`LICENSE`](LICENSE).
