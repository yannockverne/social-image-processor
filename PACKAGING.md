# Windows one-folder packaging

Social Image Processor supports a **one-folder PyInstaller distribution** on native
Windows. The executable and collected libraries stay together, which keeps PySide6
plugin loading and troubleshooting predictable.

An installer and one-file build are currently out of scope.

## Prerequisites

- Native Windows 10 or Windows 11 (64-bit).
- Python 3.12 or newer.
- A clean, activated virtual environment.
- Repository checkout including the committed icon assets.

Install development and packaging dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` currently pins PyInstaller 6.15.0. PyInstaller is a build
dependency, not an application runtime dependency.

## Build

From the repository root:

```powershell
.\build_windows.ps1
```

The build script:

1. verifies that PyInstaller is available;
2. removes previous `build/` and `dist/` directories;
3. runs the committed `social_image_processor.spec`;
4. stops on build errors;
5. verifies that the expected executable exists.

Expected artifact:

```text
dist\SocialImageProcessor\SocialImageProcessor.exe
```

Ship the entire:

```text
dist\SocialImageProcessor\
```

directory, not the executable alone.

Generated `build/` and `dist/` content must not be committed.

## Build configuration

`social_image_processor.spec` creates a windowed/no-console executable named:

```text
SocialImageProcessor.exe
```

It applies:

```text
app/assets/icons/social_image_processor.ico
```

as the Windows executable icon and bundles:

```text
app/assets/icons/social_image_processor.png
```

at the runtime resource path expected by the application.

PyInstaller's PySide6 hooks collect the required Qt libraries and plugins. After a
build, verify that the distribution contains the Windows platform plugin, normally:

```text
_internal\PySide6\plugins\platforms\qwindows.dll
```

The Trello integration uses Python standard-library networking and Windows Credential
Manager through `ctypes`; no separate credential-storage dependency is required.

The R2 integration also uses standard-library HTTP handling and requires no extra
runtime package.

Review:

```text
build\SocialImageProcessor\warn-SocialImageProcessor.txt
```

after builds and investigate relevant warnings instead of adding speculative hidden
imports.

## Native Windows validation checklist

After building, validate the packaged application rather than assuming source-run tests
cover packaging behavior.

1. Launch `dist\SocialImageProcessor\SocialImageProcessor.exe`.
2. Confirm no console window appears.
3. Confirm the application/executable icon is correct.
4. Confirm the app starts without Python being invoked manually.
5. Confirm Source / Image Processing / Publishing / Ready to Process layout renders correctly.
6. Confirm normal-window and maximized layouts remain usable.
7. Confirm input/output/watermark folder browsing works.
8. Confirm restored paths rescan correctly after relaunch.
9. Confirm PNG/JPG/JPEG source scanning and thumbnails work.
10. Confirm dynamic watermark selection, sizing, preview, missing-design validation, and export work.
11. Confirm X, Instagram, and dual-selection JPEG exports work.
12. Confirm output numbering and collision protection work.
13. Confirm Activity, progress, and Batch Metrics update correctly.
14. Close and reopen the app and confirm settings persist under `%APPDATA%`.
15. Store/read Trello credentials through Windows Credential Manager.
16. Connect to Trello and browse Board → List → Card.
17. Confirm the selected Trello card appears in the main Publishing block.
18. Configure the R2 Worker and test a real upload where appropriate.
19. Confirm a successful Worker response produces a usable public URL.
20. With R2 + Trello enabled, confirm the selected card description receives one updated `## URL MAKE` section.
21. Confirm unrelated Trello description text is preserved.
22. Confirm an R2/Trello failure does not invalidate successful local exports.
23. Confirm no `ATTACH TO CARD` workflow exists; binary Trello attachments are no longer part of the application flow.
24. If possible, copy the whole distribution folder to another Windows machine without Python installed and repeat core checks.

Also exercise:

- non-ASCII paths;
- long user paths;
- duplicate output numbering;
- repeated processing runs;
- application shutdown while idle;
- attempted shutdown while workers are active.

## Publishing integration boundary

Packaging does not change the application's integration model.

The packaged application may optionally perform:

```text
local export → Cloudflare R2 → public URL → Trello ## URL MAKE
```

The downstream Make / Buffer flow remains external. Social Image Processor does not
bundle or directly call Make, Buffer, X, or Instagram publishing APIs.

## Current packaging limitations

- no installer;
- no automatic updater;
- no one-file distribution contract;
- no code-signing workflow documented here;
- native Windows validation is still required after meaningful dependency/UI changes.
