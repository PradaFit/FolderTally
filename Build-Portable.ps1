param(
    [string]$Python = "$PSScriptRoot\.package-venv\Scripts\python.exe",
    [string]$TestPython = "$PSScriptRoot\.build-venv\Scripts\python.exe"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Build Python not found. See README.md for the build requirements.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $TestPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Packaging stopped.' }
    & $Python tools\build_portable.py
    if ($LASTEXITCODE -ne 0) { throw 'Portable build failed. Inspect the newest build log.' }
} finally {
    Pop-Location
}
