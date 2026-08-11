# Windows packaging readiness

This document prepares, but does not perform, the dedicated PyInstaller packaging
task for Social Image Processor V1 (`0.1.0`).

## Recommended approach

Use a clean Windows 10/11 Python 3.12 virtual environment. Install the locked-range
application requirements, then install PyInstaller as a separate packaging tool:

```powershell
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6.10,<7"
pyinstaller --noconfirm --clean --windowed --name SocialImageProcessor app/main.py
```

For the first packaging iteration, generate and commit a reviewed
`SocialImageProcessor.spec` rather than maintaining a complex hand-written spec.
Build from that spec after adding an icon or data files:

```powershell
pyinstaller --noconfirm --clean SocialImageProcessor.spec
```

Do not add PyInstaller to runtime requirements. Record the exact successful
packaging-tool version in the dedicated packaging change.

## Entry point and paths

`app/main.py` is the single entry point and importing it does not launch Qt. The app
has no repository-relative runtime data paths. User-selected image folders are
absolute/persisted paths, and settings are resolved through `%APPDATA%` to
`SocialImageProcessor/settings.json`, never beside the executable.

## PySide6 considerations

PyInstaller's maintained PySide6 hooks should collect Qt modules, platform plugins,
and required Qt data used by the imported widgets. The current application uses
standard QtCore, QtGui, and QtWidgets APIs and does not require a custom hidden
import. Validate that `platforms/qwindows.dll` is present in the collected build.
Only add hidden imports or Qt data entries if PyInstaller analysis/runtime warnings
show a concrete omission.

## Assets

There is currently no runtime `assets/` directory and no application icon. A future
`.ico` file is optional but should be added deliberately and referenced with
`--icon` or the spec's `icon=` setting. Do not collect the README, tests, user
images, watermarks, or settings into the executable. If runtime assets are added
later, resolve bundled files through a small explicit resource helper rather than
the current working directory.

## Dedicated packaging validation

The packaging task should test both one-folder and, if desired, one-file modes on a
clean Windows machine. Validate startup/relaunch, `%APPDATA%` settings, Browse,
thumbnail/preview workers, exact/missing/ambiguous watermark behavior, dual export,
atomic writes, duplicate numbering, non-ASCII and long user paths, relaunch after
processing, and absence of console windows. Run the automated suite before building
and retain the PyInstaller warnings/build log for review.

Do not add installer technology or publish an executable until the packaged build
has received separate approval.
