$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Desktop = Join-Path $Root "desktop"
$Version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()

Push-Location $Desktop
try {
    if (-not (Test-Path ".venv")) {
        py -3.13 -m venv .venv
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    & .\.venv\Scripts\python.exe -m compileall -q gt_super_controller tests
    & .\.venv\Scripts\python.exe -m pytest
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GT_SUPER_CONTROLLER.spec

    $Output = Join-Path $Root "dist\windows"
    New-Item -ItemType Directory -Force -Path $Output | Out-Null
    $Name = "GT_SUPER_CONTROLLER_$Version.exe"
    Copy-Item "dist\GT_SUPER_CONTROLLER.exe" (Join-Path $Output $Name) -Force
    $Hash = Get-FileHash (Join-Path $Output $Name) -Algorithm SHA256
    "{0} *{1}" -f $Hash.Hash.ToLowerInvariant(), $Name |
        Set-Content (Join-Path $Output "SHA256SUMS_WINDOWS.txt") -Encoding ascii
}
finally {
    Pop-Location
}
