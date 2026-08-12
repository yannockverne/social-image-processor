# Windows one-folder packaging

Social Image Processor is packaged as a **one-folder** PyInstaller distribution
for this milestone. Keeping the executable and its collected libraries together
makes startup, PySide6 plugin loading, and troubleshooting more reliable than an
initial one-file build. An installer is **not** part of this milestone. One-file
packaging may be evaluated later, after the one-folder distribution is validated.

## Prerequisites

- Native Windows 10 or Windows 11 (64-bit).
- Python 3.12 or newer and a clean, activated virtual environment.
- The repository checked out without modifying the committed icon assets.

Install the application, test, and pinned packaging dependencies into the active
environment:

```powershell
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` pins PyInstaller 6.15.0 for repeatable builds; PyInstaller
is not an application runtime dependency.

## Build

From the repository root, run:

```powershell
.\build_windows.ps1
```

The script uses the active environment's `python`, verifies PyInstaller is
available, removes old `build/` and `dist/` directories, and builds the committed
`social_image_processor.spec`. It stops on errors and verifies the final artifact.

Expected executable:

```text
dist/SocialImageProcessor/SocialImageProcessor.exe
```

Ship the entire `dist/SocialImageProcessor/` directory, not the executable alone.
Generated `build/` and `dist/` content must not be committed.

## Build configuration

The spec creates the windowed (no-console) `SocialImageProcessor.exe` and applies
`app/assets/icons/social_image_processor.ico` to the Windows executable. It bundles
the runtime PNG at its resource loader's expected path:
`app/assets/icons/social_image_processor.png`. Paths are relative to the repository
and bundle roots; no machine-specific path is embedded.

PyInstaller's maintained PySide6 hooks collect the imported QtCore, QtGui, and
QtWidgets libraries and Qt plugins. After building, confirm that the distribution
contains the Windows platform plugin (normally `_internal/PySide6/plugins/platforms/qwindows.dll`).
The Trello client uses Python's standard-library networking, while Credential
Manager uses Windows `ctypes`; neither requires a separately bundled package.

Review `build/SocialImageProcessor/warn-SocialImageProcessor.txt` after every build.
Investigate relevant missing-module warnings rather than adding speculative hidden
imports.

## Native Windows validation checklist

1. Launch `dist/SocialImageProcessor/SocialImageProcessor.exe`.
2. Confirm no console window appears.
3. Confirm the correct icon appears on the executable, taskbar, and app window.
4. Confirm the app starts without `python -m app.main`.
5. Confirm folder browsing works.
6. Confirm source image scanning works.
7. Confirm image processing and JPEG export work.
8. Confirm exact-match, missing, and ambiguous watermark handling works.
9. Close and reopen the app and confirm settings persist under `%APPDATA%`.
10. Store and read Trello credentials through Windows Credential Manager.
11. Connect to Trello with real credentials.
12. Browse Board → List → Card.
13. Use **ATTACH TO CARD** with real files processed in the current batch.
14. Confirm shared Trello activity messages appear in the activity log.
15. If possible, copy the complete distribution folder to another Windows machine
    without Python installed and repeat the checks.

Also exercise non-ASCII and long user paths, duplicate output numbering, dual X and
Instagram exports, relaunch after processing, and application shutdown while idle.
