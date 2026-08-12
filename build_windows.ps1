$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = $PSScriptRoot
Set-Location $RepositoryRoot

try {
    & python -m PyInstaller --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller returned exit code $LASTEXITCODE."
    }
}
catch {
    Write-Error "PyInstaller is unavailable in the active Python environment. Run: python -m pip install -r requirements-dev.txt"
    exit 1
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "build", "dist"

& python -m PyInstaller --noconfirm --clean "social_image_processor.spec"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

$Executable = Join-Path $RepositoryRoot "dist\SocialImageProcessor\SocialImageProcessor.exe"
if (-not (Test-Path $Executable -PathType Leaf)) {
    Write-Error "PyInstaller completed but the expected executable was not found: $Executable"
    exit 1
}

Write-Host "Build succeeded: $Executable"
