<#
.SYNOPSIS
    Automates testing and submission of Trinetra manifests to Windows Package Manager (winget-pkgs).
.DESCRIPTION
    Uses Microsoft's official wingetcreate tool to validate manifests locally and optionally submit PR to microsoft/winget-pkgs.
#>

param(
    [switch]$Submit = $false,
    [string]$GitHubToken = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== Trinetra Windows Package Manager (winget) Tool ===" -ForegroundColor Cyan

# Check if winget is available
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Warning "winget is not detected on this system. (Requires Windows 10/11 with App Installer)."
}

# Check if wingetcreate is installed
if (-not (Get-Command wingetcreate -ErrorAction SilentlyContinue)) {
    Write-Host "Installing wingetcreate CLI..." -ForegroundColor Yellow
    winget install Microsoft.WingetCreate --accept-source-agreements --accept-package-agreements
}

$manifestDir = Join-Path $PSScriptRoot "winget"

Write-Host "Validating manifests in $manifestDir..." -ForegroundColor Green
wingetcreate validate $manifestDir

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCCESS] Winget manifests are 100% valid!" -ForegroundColor Green
    if ($Submit) {
        if (-not $GitHubToken) {
            $GitHubToken = $env:GITHUB_TOKEN
        }
        if (-not $GitHubToken) {
            Write-Error "Please provide -GitHubToken <TOKEN> or set GITHUB_TOKEN environment variable to submit to microsoft/winget-pkgs."
        }
        Write-Host "Submitting PR to microsoft/winget-pkgs..." -ForegroundColor Cyan
        wingetcreate submit $manifestDir --token $GitHubToken
    } else {
        Write-Host "`nTo submit to microsoft/winget-pkgs directly, run:" -ForegroundColor Yellow
        Write-Host "  .\distribution\submit_to_winget.ps1 -Submit -GitHubToken <YOUR_GITHUB_PAT>" -ForegroundColor White
    }
} else {
    Write-Error "Winget manifest validation failed."
}
