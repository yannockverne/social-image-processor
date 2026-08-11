# Project Context

This file records implementation decisions already made for Social Image Processor.

`SPEC.md` remains the functional source of truth.

The purpose of this file is to preserve architectural and workflow decisions across independent Codex tasks.

---

## Current project state

Completed and merged into `main`:

- Phase 1 — project foundation, domain models, profiles, settings
- Phase 2 — input scanning and exact-resolution watermark catalog
- Phase 3 — core image processing, exact watermark compositing, JPEG export, safe output naming

Next phase:

- Phase 4 — batch processing orchestration, results, progress, and statistics

Do not reimplement completed phases unless fixing a concrete regression.

---

## Core architecture

Keep dependency direction simple:

UI
→ services / orchestration
→ models + core processing

Rules:

- `app/core` must remain independent of Qt.
- Core image processing uses Pillow, not PySide6.
- Services should expose synchronous, testable operations.
- Qt workers will later adapt synchronous services to background execution.
- UI widgets must not contain Pillow processing logic.
- Full-resolution image objects must not be retained in GUI/domain models.
- Avoid unnecessary frameworks and over-engineering.

---

## Source images

Supported V1 input formats:

- PNG
- JPG
- JPEG

Input scanning is:

- non-recursive;
- case-insensitive by extension;
- predictably sorted by filename.

Use raw stored pixel dimensions.

Do not apply EXIF orientation transformations in V1.

The source image must never be modified.

---

## Platform profiles

V1 has separate X and Instagram profiles.

### X

- JPEG
- prefix: `X_`
- preserve source dimensions
- no crop
- no resize

### Instagram

- JPEG
- prefix: `Insta_`
- preserve source dimensions
- no crop
- no resize

Per-image X and Instagram selections default to unchecked.

The profiles remain distinct even though their current processing behavior is nearly identical.

---

## Watermark model

The watermark workflow is intentionally strict.

A watermark is a full-canvas transparent PNG prepared at the exact target resolution.

Example:

- source: `3440x1440`
- watermark: `3440x1440`

The watermark is conceptually equivalent to placing the prepared PNG as the top Photoshop layer.

Rules:

- exact source/watermark dimensions are required;
- watermark is mapped one-to-one at origin `(0, 0)`;
- no watermark scaling;
- no repositioning;
- no margin calculation;
- no percentage-based sizing;
- no crop;
- no aspect-ratio fallback;
- no same-ratio automatic fallback in V1.

Matching is based on actual watermark pixel dimensions, not filenames.

Watermark status can be:

- exact
- missing
- ambiguous

If multiple watermark files have the same dimensions, the match is ambiguous.

When watermarking is enabled:

- missing watermark → skip source
- ambiguous watermark → skip source

Never silently choose between duplicate watermark candidates.

---

## Image processing

Phase 3 established these rules:

- source and watermark dimensions must match exactly;
- mismatch produces a typed error;
- mismatch must never trigger automatic scaling;
- composite source and watermark at full source resolution;
- convert safely to RGBA as needed;
- alpha-composite watermark at `(0, 0)`;
- flatten transparency before JPEG output;
- default background is `#000000`;
- output dimensions must equal source dimensions;
- no crop;
- no resize;
- final JPEG is RGB;
- JPEG quality defaults to 92.

The term "pixel-perfect watermark" means one-to-one watermark canvas mapping before lossy JPEG encoding.

---

## Metadata

V1 does not guarantee metadata identity.

Rules:

- do not apply EXIF orientation transformations;
- do not blindly copy EXIF orientation metadata;
- ICC profile may be preserved when straightforward and safe;
- framing and pixel dimensions are more important than metadata preservation.

---

## Output naming and safety

Generated filenames use platform prefixes:

- `X_name.jpg`
- `Insta_name.jpg`

If a file exists:

- `X_name_2.jpg`
- `X_name_3.jpg`
- etc.

Filename allocation must account for:

- existing files on disk;
- paths already reserved during the current batch;
- Windows case-insensitive collisions.

Never overwrite existing outputs.

Input and output folders must not be identical in V1.

Output writes should use safe/atomic finalization where practical.

A failed write must not leave a misleading completed JPEG.

---

## Settings

Settings are stored as JSON.

Primary Windows location:

`%APPDATA%/SocialImageProcessor/settings.json`

Persist at least:

- input folder
- output folder
- watermark folder
- JPEG quality
- watermark enabled
- background color

JPEG quality:

- default: 92
- UI range: 70–100

Corrupted or incomplete settings must recover safely to defaults.

Do not add a configuration framework such as Pydantic unless a concrete need appears.

---

## Phase 4 approved behavior

Phase 4 should implement a Qt-independent batch processor.

Progress:

- count by selected source image, not generated output;
- progress must be monotonic.

Selection behavior:

- neither platform selected → ignore source
- X only → one X output
- Instagram only → one Instagram output
- both → both outputs

When both outputs share identical processing settings, decode/composite the source once where practical.

Watermark behavior:

- watermark disabled → export without watermark
- watermark enabled + exact match → export with watermark
- watermark enabled + missing match → skip full source
- watermark enabled + ambiguous match → skip full source

Failures:

- one corrupt source must not stop later sources;
- one failed platform output must not stop the batch;
- errors should be represented as structured results.

Statistics:

- count each successfully processed source once;
- do not double-count a source that creates two outputs;
- sum every successfully generated output file;
- wholly skipped or failed sources are excluded;
- if one of two outputs succeeds, count source once and only successful output bytes;
- negative savings/reduction are valid and must not be clamped.

No cancellation in V1.

---

## Features explicitly deferred

Do not implement yet:

- drag and drop
- crop editor
- automatic Instagram 4:5 preparation
- watermark scaling fallback
- per-image watermark overrides
- custom platform preset editor
- metadata policy UI
- EXIF stripping toggle
- WebP / AVIF
- advanced batch renaming
- direct Make integration
- Buffer integration
- direct social publishing
- Photoshop integration
- actual PyInstaller distribution build

Keep the architecture extensible enough for later work, but do not build unused frameworks for these future features.

---

## Development workflow

For each new phase:

1. Start from the latest `main`.
2. Read `SPEC.md` completely.
3. Read `PROJECT_CONTEXT.md` completely.
4. Inspect existing implementation and tests.
5. Implement only the requested phase.
6. Run relevant tests/checks.
7. Fix failures.
8. Commit the phase.
9. Stop before the next phase.
10. Merge through a Pull Request into `main`.

Prefer a fresh Codex task based on the latest `main` after each merged phase.