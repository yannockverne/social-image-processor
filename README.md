Social Image Processor

A lightweight Windows desktop application for preparing image exports for social-media publishing workflows.

Social Image Processor is designed for photographers, virtual photographers, and content creators who regularly export large PNG files and need a fast, repeatable way to:

convert images to optimized JPEG files;

generate platform-specific versions for X and Instagram;

apply prepared full-frame watermarks automatically;

avoid accidentally publishing an image without its watermark;

reduce file sizes before sending images through automation tools such as Make or Buffer.

The application is built with Python, PySide6, and Pillow.

Project status

Current state: functional V1 implementation in progress.

Implemented so far:

project architecture and persistent settings;

source image scanning;

exact-resolution watermark discovery;

PNG/JPG/JPEG support;

strict full-frame watermark compositing;

JPEG export;

safe output naming;

batch processing;

processing statistics;

PySide6 desktop interface;

non-blocking thumbnails and previews;

background processing workers;

X / Instagram per-image selection;

processing log and progress display.

The remaining V1 work focuses primarily on hardening, end-to-end Windows validation, documentation refinement, and packaging readiness.

Why this project exists

Large PNG screenshots can easily reach 10–20 MB per image.

That is excellent for editing and archival work, but less useful when the final image is going to be uploaded to social networks and transferred through automation services with bandwidth or data-transfer limits.

The intended workflow is:

Photoshop export
        ↓
Social Image Processor
        ↓
Optimized JPG + optional watermark
        ↓
Make / Buffer / manual publishing
        ↓
X / Instagram

The original source image is never modified.

Main features

Image preparation

Supports PNG, JPG, and JPEG source images.

Converts final exports to JPEG.

Configurable JPEG quality.

Default JPEG quality: 92.

Preserves source pixel dimensions.

No automatic crop.

No automatic resize.

Handles RGB, RGBA, grayscale, and palette-based images.

Flattens transparency safely before JPEG export.

Platform exports

Each source image can independently be selected for:

X

Instagram

both

Generated filenames use platform prefixes:

X_M50_001.jpg
Insta_M50_001.jpg

If a file already exists, it is never overwritten:

X_M50_001.jpg
X_M50_001_2.jpg
X_M50_001_3.jpg

Watermark workflow

The watermark system intentionally reproduces a simple Photoshop workflow.

A watermark is not just a logo image.

It is a transparent PNG containing a full image-sized canvas, with the logo already positioned exactly where it should appear.

Example:

Source image:
3440 × 1440

Watermark:
3440 × 1440 transparent PNG

The watermark is composited over the source image one-to-one at (0, 0), just like placing the prepared watermark file as the top Photoshop layer.

There is:

no percentage-based watermark sizing;

no automatic positioning;

no scaling;

no aspect-ratio fallback;

no automatic crop.

Watermark matching is based on the actual pixel dimensions of the watermark file, not its filename.

Possible watermark states are:

Exact — one matching watermark exists;

Missing — no watermark exists for that resolution;

Ambiguous — multiple watermark files share the same resolution.

When watermarking is enabled, images with missing or ambiguous watermarks are skipped rather than exported without one.

This is intentional: preventing accidental unwatermarked publishing is one of the main purposes of the application.

Desktop interface

The PySide6 interface includes:

Input folder selector;

Output folder selector;

Watermark folder selector;

source image table;

asynchronous thumbnails;

filename, dimensions, and source file size;

X selection checkbox;

Instagram selection checkbox;

watermark status;

bulk selection controls;

large image preview;

watermark preview;

global watermark toggle;

JPEG-quality control;

processing progress;

human-readable processing log;

final file-size statistics.

The interface is designed to remain usable at both:

1920 × 1080

3440 × 1440

Requirements

Runtime

Windows 10 or Windows 11

Python 3.12+

Main dependencies

PySide6

Pillow

Development / testing

pytest

Ruff

Dependencies are declared in requirements.txt.

Installation

1. Clone the repository

Using Git:

git clone https://github.com/yannockverne/social-image-processor.git
cd social-image-processor

Alternatively, the repository can be cloned using GitHub Desktop.

2. Create a virtual environment

python -m venv .venv

Activate it:

.\.venv\Scripts\Activate.ps1

3. Install dependencies

python -m pip install --upgrade pip
pip install -r requirements.txt

Running the application

From the repository root:

python -m app.main

The desktop application should open normally.

Basic usage

Select an Input folder containing source images.

Select an Output folder.

Select the folder containing your watermark PNG files.

Wait for the source image list and thumbnails to load.

Select X, Instagram, or both for the images you want to export.

Enable or disable Apply watermark.

Adjust JPEG quality if required.

Review the preview and watermark status.

Click PROCESS IMAGES.

Review the processing log and final size statistics.

The Input and Output folders must be different.

Watermark folder

Watermark filenames are not technically required to follow a specific convention because matching is based on actual image dimensions.

However, descriptive names are recommended.

Example:

Watermarks/
├── watermark_3440x1440.png
├── watermark_3840x2160.png
├── watermark_3000x4000.png
└── watermark_4000x5000.png

Each file should:

be a PNG;

have the same canvas resolution as its intended source image;

contain transparency where the original image should remain visible;

already contain the logo in its final desired position.

Settings

Application settings are stored locally.

On Windows, the default location is:

%APPDATA%\SocialImageProcessor\settings.json

Persisted settings include:

Input folder;

Output folder;

Watermark folder;

JPEG quality;

watermark enabled state;

transparency-flattening background color.

No account information, credentials, or secrets are stored.

Privacy and network access

Social Image Processor is designed to work entirely offline.

It does not require:

an account;

a cloud service;

an external API;

telemetry;

network access.

The application does not directly publish content to social networks.

Project structure

The project uses a layered architecture:

social-image-processor/
├── app/
│   ├── main.py
│   ├── core/
│   ├── models/
│   ├── services/
│   ├── ui/
│   └── utils/
├── tests/
├── assets/
├── SPEC.md
├── PROJECT_CONTEXT.md
├── README.md
├── requirements.txt
└── LICENSE

Dependency direction is intentionally simple:

UI
 ↓
Services / orchestration
 ↓
Models + core image processing

Important architecture rules:

core image-processing code does not depend on Qt;

UI widgets do not contain Pillow processing logic;

processing services remain synchronously testable;

Qt workers adapt synchronous services to background execution;

full-resolution images are not retained in table models;

source images are opened, processed, and released progressively.

Running tests

Run the complete test suite:

pytest

For an offscreen Qt test run:

$env:QT_QPA_PLATFORM="offscreen"
pytest

Run Ruff lint checks:

ruff check app tests

Check formatting:

ruff format --check app tests

Compile Python modules:

python -m compileall -q app tests

Design principles

The V1 follows a few deliberately strict rules:

Source images are never modified.

Source images are never automatically cropped.

Source images are never automatically resized.

Watermarks are exact-resolution full-frame overlays.

Missing watermarks do not silently fall back to another file.

Existing exports are never overwritten.

Image-processing failures should not terminate the whole batch.

The application should remain responsive while processing large screenshots.

The processing engine remains independent of the GUI.

Functionality and reliability take priority over unnecessary framework complexity.

Metadata and color profiles

V1 guarantees preservation of:

image framing;

raw output pixel dimensions.

V1 does not guarantee metadata identity.

In particular:

EXIF orientation transformations are not applied automatically;

EXIF metadata is not blindly copied;

ICC color profiles may be preserved when doing so is straightforward and safe.

Planned improvements

Potential future features include:

standalone Windows executable via PyInstaller;

drag and drop;

per-image watermark overrides;

optional watermark fallback scaling;

crop editor;

automatic Instagram 4:5 preparation;

custom platform presets;

additional output formats such as WebP or AVIF;

advanced batch renaming;

before/after comparison;

Photoshop integration;

optional Make or Buffer integration.

These features are deliberately outside the initial V1 scope.

Development notes

The functional source of truth for V1 is:

SPEC.md

Cross-task architectural decisions and project conventions are recorded in:

PROJECT_CONTEXT.md

Development is intentionally performed in reviewable phases, with each completed phase merged into main through a Pull Request.

License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

See the LICENSE file for details.

Author

Created by Yannock Verne as a personal workflow tool for image preparation and social-media publishing.

Built with a strong focus on virtual photography, large-format screenshots, predictable watermarking, and automation-friendly JPEG exports.
