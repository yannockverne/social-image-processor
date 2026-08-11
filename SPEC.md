# Social Image Processor — V1 Specification

## 1. Project overview

**Project name:** Social Image Processor  
**Repository:** `yannockverne/social-image-processor`

Social Image Processor is a Windows desktop application used to prepare image exports for social-media publishing workflows.

Typical workflow:

Photoshop export  
→ Social Image Processor  
→ optimized JPG files with optional watermark  
→ publishing workflow through Make / Buffer / social networks

Primary goals:

- reduce image file size before transfer through Make;
- prevent publishing images without the intended watermark;
- generate platform-specific X and Instagram exports;
- preserve the original source files at all times;
- keep the workflow fast and visually predictable.

---

## 2. Target platform and stack

Use:

- Python 3.12+
- PySide6 for the desktop GUI
- Pillow for image processing
- pytest for automated tests

Target:

- Windows 10
- Windows 11

The application should later be packageable as a standalone `.exe` with PyInstaller.

Do not use Electron or a web frontend.

The application must work fully offline and must not require any account, cloud service, external API, telemetry, or network access.

---

## 3. Architecture

Keep the code modular and maintainable.

Suggested structure:

```text
social-image-processor/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ ui/
│  ├─ core/
│  ├─ models/
│  ├─ services/
│  └─ utils/
├─ tests/
├─ assets/
├─ README.md
├─ requirements.txt
└─ .gitignore
```

This structure may be adjusted if a cleaner architecture is justified.

Do not build the application as one large monolithic Python file.

---

## 4. Main workflow

The user selects:

1. an **Input folder** containing source images;
2. an **Output folder** receiving processed files;
3. a **Watermark folder** containing transparent full-frame watermark PNG files.

The application scans the input directory and displays supported images in a graphical list.

Each image can independently be marked for:

- X export;
- Instagram export.

The same source image may be exported to both platforms.

Example:

```text
Source:
M50_001.png

Outputs:
X_M50_001.jpg
Insta_M50_001.jpg
```

The source image must **never** be modified.

---

## 5. Main window

Top controls:

```text
Input Folder:      [ path ] [ Browse ]
Output Folder:     [ path ] [ Browse ]
Watermark Folder:  [ path ] [ Browse ]
```

Remember the last selected folders between launches.

Below the folder controls, display the image list.

Also provide a global checkbox:

```text
[✓] Apply watermark
```

A prominent processing button should be available:

```text
PROCESS IMAGES
```

---

## 6. Image list

Display one row per source image.

Columns:

- Thumbnail
- Filename
- Dimensions
- File size
- X checkbox
- Instagram checkbox
- Watermark status

Example:

```text
Preview | Filename     | Dimensions | Size    | X | Insta | Watermark
-----------------------------------------------------------------------
[img]   | M50_001.png | 3440x1440  | 14 MB   | ✓ |       | ✓
[img]   | M50_002.png | 4000x5000  | 11 MB   |   | ✓     | ✓
[img]   | M50_003.png | 7680x4320  | 18 MB   | ✓ | ✓     | ⚠ Missing
```

Supported source formats for V1:

- PNG
- JPG
- JPEG

Generate thumbnails asynchronously when practical so loading a folder containing large screenshots does not freeze the GUI.

Avoid loading full-resolution images solely to create the visible thumbnail.

Selecting a row should update the preview panel.

Provide global controls:

```text
Select all X
Clear all X

Select all Instagram
Clear all Instagram
```

---

## 7. Platform export profiles

Create separate profiles for X and Instagram.

### X profile — V1 defaults

- Output format: JPG
- JPEG quality: 92
- Keep original dimensions
- No automatic crop
- Filename prefix: `X_`

Example:

```text
X_M50_001.jpg
```

### Instagram profile — V1 defaults

- Output format: JPG
- JPEG quality: 92
- Preserve original dimensions in V1
- No automatic crop
- Filename prefix: `Insta_`

Example:

```text
Insta_M50_001.jpg
```

The application must **never automatically crop an image**.

Image framing is considered an intentional artistic choice.

If an image does not match a preferred Instagram aspect ratio, preserve the source framing in V1.

---

## 8. JPEG conversion

Default JPEG quality:

```text
92
```

Expose JPEG quality in the settings UI.

Recommended selectable range:

```text
70–100
```

When converting a PNG with transparency to JPEG, flatten transparency against a configurable background.

Default background:

```text
black
```

Do not alter source dimensions unless a future explicitly enabled profile requires it.

---

# 9. Watermark system

## 9.1 Core principle

The watermark system must reproduce an existing Photoshop workflow.

A watermark file is **not just a logo asset**.

It is a **full-canvas transparent PNG**, already created at a specific target resolution, with the logo positioned exactly where the user wants it.

Example:

```text
Source image:
3440 × 1440

Watermark file:
3440 × 1440 transparent PNG
```

The watermark is applied exactly like placing the prepared watermark PNG as the top Photoshop layer.

Therefore:

- do **not** calculate watermark size from percentages;
- do **not** calculate logo placement;
- do **not** automatically reposition the logo;
- do **not** automatically scale a watermark during the normal V1 workflow;
- do **not** infer placement from aspect ratio.

When dimensions match, composite the full watermark canvas over the source image **pixel-for-pixel at 100% scale**.

This full-frame exact-resolution behavior is the authoritative watermark logic for V1.

---

## 9.2 Watermark discovery

The application scans the selected Watermark folder.

It should inspect the actual pixel dimensions of each watermark PNG rather than relying exclusively on filenames.

Example folder:

```text
Watermarks/
├─ watermark_3440x1440.png
├─ watermark_4000x5000.png
├─ watermark_3000x4000.png
└─ watermark_3840x2160.png
```

Filenames may follow this convention, but matching should ultimately be based on image dimensions.

The application should build an internal mapping such as:

```text
3440x1440 → watermark_3440x1440.png
4000x5000 → watermark_4000x5000.png
3000x4000 → watermark_3000x4000.png
```

If several watermark files have the same dimensions, report the ambiguity clearly rather than silently choosing an arbitrary one.

---

## 9.3 Exact matching

For each source image, search for a watermark whose dimensions exactly match the source dimensions.

Example:

```text
M50_001.png
3440 × 1440

→ use watermark whose canvas is exactly:
3440 × 1440
```

The watermark should be alpha-composited directly over the image.

No resize or placement calculation is required.

---

## 9.4 Missing watermark behavior

Preventing accidental unwatermarked publishing is one of the primary purposes of this application.

Therefore, when:

```text
Apply watermark = enabled
```

and no exact-resolution watermark exists for an image, the application must show a visible warning before processing.

The row should display something similar to:

```text
⚠ Missing
```

The processing log should state:

```text
WARNING: No exact 7680x4320 watermark found for M50_003.png
```

### V1 default safety behavior

If watermarking is globally enabled and the selected image has no exact matching watermark:

**do not export that image.**

Mark it as skipped and continue processing the rest of the batch.

Example:

```text
SKIPPED M50_003.png
Reason: watermark enabled but no exact 7680x4320 watermark exists
```

A single missing watermark must never stop the rest of the batch.

If the user wants an unwatermarked export, they can explicitly disable the global watermark checkbox.

This behavior should make accidentally forgetting the watermark difficult.

---

## 9.5 Future watermark fallback

Do **not** implement automatic same-ratio scaling in V1.

The architecture may later allow an optional explicit fallback such as:

```text
No exact watermark found.
Use a proportionally scaled same-ratio watermark?
```

But this must not be part of normal V1 automatic behavior.

For V1:

```text
Exact dimensions → use watermark
No exact dimensions → warn and skip
```

---

## 10. Preview panel

Add a preview area.

When an image row is selected:

- display a scaled preview of the source image;
- if watermarking is enabled and an exact matching watermark exists, display the composited result;
- if no matching watermark exists, clearly indicate that the watermark is missing.

The preview does not need to use full-resolution rendering.

Its purpose is visual confirmation.

The preview should preserve the source aspect ratio.

---

## 11. Output file handling

Never overwrite source files.

All exports go to the selected Output folder.

If an output filename already exists, create a numbered filename.

Example:

```text
X_M50_001.jpg
X_M50_001_2.jpg
X_M50_001_3.jpg
```

This behavior may become configurable later.

---

## 12. Processing behavior

When the user clicks:

```text
PROCESS IMAGES
```

For every listed source image:

- if X is checked, create an X export;
- if Instagram is checked, create an Instagram export;
- if both are checked, create both;
- if neither is checked, ignore the image.

If watermarking is enabled:

- require an exact-resolution watermark;
- composite it pixel-for-pixel;
- skip images that lack a matching watermark.

Then convert the result to JPEG using the relevant platform profile.

One failed image must not stop the batch.

---

## 13. Background processing and responsiveness

Processing must not freeze the GUI.

Use an appropriate PySide6 worker mechanism such as:

- QThread;
- QThreadPool / QRunnable;
- another clean Qt-compatible worker architecture.

Display a progress bar and progress text.

Example:

```text
Processing image 3 / 12
```

Thumbnail generation should also avoid blocking the UI for large image folders where practical.

---

## 14. Processing log

Include a visible log panel.

Example:

```text
M50_001.png
→ X_M50_001.jpg
14.2 MB → 2.4 MB

M50_002.png
→ Insta_M50_002.jpg
11.8 MB → 1.9 MB

SKIPPED M50_003.png
No exact 7680x4320 watermark found.
```

Errors should be clear and human-readable.

Examples:

- corrupted source image;
- output permission denied;
- missing watermark;
- ambiguous watermark;
- failed JPEG write.

A failure must not crash the entire application.

---

## 15. Size statistics

After processing, display:

- total source size for processed source images;
- total generated output size;
- bytes saved;
- percentage reduction.

Example:

```text
Source:
126.4 MB

Output:
22.1 MB

Saved:
104.3 MB

Reduction:
82.5 %
```

Only final post-processing statistics are required for V1.

Estimated output size before processing is optional and not required.

---

## 16. Settings

Store local settings as JSON.

Suggested location:

```text
%APPDATA%/SocialImageProcessor/settings.json
```

Store at minimum:

- input directory;
- output directory;
- watermark directory;
- JPEG quality;
- watermark enabled.

Optionally store:

- window size;
- window position;
- other harmless UI preferences.

Do not store secrets.

If the settings file is absent or corrupted, restore sensible defaults without crashing.

---

## 17. Error handling

Gracefully handle:

- invalid image files;
- corrupted images;
- missing folders;
- inaccessible folders;
- missing watermark files;
- duplicate watermark dimensions;
- unsupported file formats;
- permission errors;
- output write errors.

A single broken file must not stop the full batch.

---

## 18. Performance

Typical source images may include:

```text
3440x1440
4000x5000
3000x4000
7680x4320
8K screenshots
```

PNG files may be 10–20 MB or larger.

Avoid unnecessary copies of full-resolution images in memory.

Do not keep every full-resolution source image loaded simultaneously.

Open/process/release images progressively during batch operations.

---

## 19. Automated tests

Use pytest.

At minimum create tests for non-GUI core behavior:

- watermark discovery;
- exact dimension matching;
- missing watermark detection;
- duplicate watermark dimension handling;
- full-frame watermark alpha compositing;
- output filename generation;
- duplicate output filename numbering;
- PNG → JPEG conversion;
- profile selection;
- source file remains unchanged.

Tests should create temporary generated images instead of requiring user assets.

---

## 20. README

Create a useful `README.md` covering:

- project purpose;
- current features;
- supported input formats;
- requirements;
- dependency installation;
- how to launch the application;
- how to run tests;
- watermark workflow;
- expected full-frame watermark behavior;
- architecture overview;
- future PyInstaller packaging instructions.

Suggested run command:

```bash
python -m app.main
```

Suggested test command:

```bash
pytest
```

---

## 21. UI style

Use a clean, modern, dark-friendly interface.

Do not spend excessive development time on custom styling during the first implementation.

Functionality and reliability take priority over visual polish.

Prefer standard PySide6 layouts and widgets.

The UI should work comfortably at:

- 1920×1080;
- 3440×1440.

Avoid assumptions that require an ultrawide monitor.

---

## 22. Non-negotiable design rules

1. The source image is **never modified**.
2. No automatic crop.
3. No destructive operation on source files.
4. All generated files go to the selected Output folder.
5. Watermark V1 uses **exact-resolution full-frame transparent PNG overlays**.
6. No percentage-based automatic watermark sizing in V1.
7. No automatic watermark placement calculation in V1.
8. If watermarking is enabled and no exact watermark exists, **skip the affected image**.
9. Application works offline.
10. No telemetry.
11. No network dependency.
12. No account/login requirement.

---

## 23. Future features — not part of V1

The architecture may allow these later, but do not implement them in the initial V1:

- drag and drop;
- custom crop editor;
- automatic Instagram 4:5 preparation;
- user-defined platform presets;
- per-image watermark override;
- same-ratio watermark scaling fallback;
- alternative watermark positions;
- EXIF stripping toggle;
- WebP / AVIF output;
- advanced batch renaming;
- before/after image comparison;
- Make API integration;
- Buffer API integration;
- direct social-network publishing;
- Photoshop integration.

Do not over-engineer V1 around future features.

---

# 24. Definition of done for the first functional V1

The first functional V1 should provide:

- clean project structure;
- working PySide6 main window;
- Input / Output / Watermark folder selection;
- persistent folder settings;
- image scanning;
- asynchronous or non-blocking thumbnail loading;
- thumbnails;
- file dimensions and source size display;
- X checkbox per image;
- Instagram checkbox per image;
- global selection/clear controls;
- global watermark checkbox;
- automatic exact-resolution watermark discovery;
- visible missing-watermark status;
- preview with watermark when available;
- JPEG conversion;
- full-frame pixel-perfect watermark compositing;
- safe skip behavior when watermark is missing;
- background batch processing;
- progress bar;
- processing log;
- output size statistics;
- duplicate output filename protection;
- robust error handling;
- local JSON settings;
- automated core tests;
- README.

---

# 25. Implementation approach

Do not implement the entire application as one giant unreviewable change.

Before coding:

1. Read this specification completely.
2. Inspect the repository.
3. Propose an implementation plan divided into sensible phases.
4. Identify any ambiguity or technical concern that materially affects the V1 design.
5. Do **not** modify files until the plan has been reviewed.

Once implementation is authorized:

1. implement one coherent phase at a time;
2. run relevant tests after each phase;
3. keep responsibilities separated between UI and image-processing logic;
4. fix failures before moving on;
5. report what changed and how it was validated.

The specification in this file is the functional source of truth for V1.
