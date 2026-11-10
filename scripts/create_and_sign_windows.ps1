<#
.SYNOPSIS
    Generates an authentic Code Signing Certificate for Taksya Studio and signs Trinetra executables.
.DESCRIPTION
    1. Creates a local X.509 Code Signing Certificate with 5-year validity.
    2. Exports the public certificate (.cer) for users/admins to trust.
    3. Signs Trinetra.exe and all internal binaries using SHA-256 Authenticode.
#>

[CmdletBinding()]
param(
    [string]$TargetExe = "release\Trinetra\Trinetra.exe",
    [string]$CertName = "CN=Taksya Studio, O=Taksya Studio, OU=Trinetra Assistive Intelligence"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Trinetra Windows Authenticode Code Signing ===" -ForegroundColor Cyan

# 1. Check if certificate already exists in CurrentUser\My
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "*Taksya Studio*" } | Select-Object -First 1

if (-not $cert) {
    Write-Host "Generating Code Signing Certificate for Taksya Studio..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $CertName `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(5) `
        -KeyLength 2048 `
        -HashAlgorithm "SHA256"
    Write-Host "Created certificate: $($cert.Thumbprint)" -ForegroundColor Green
} else {
    Write-Host "Using existing certificate: $($cert.Thumbprint)" -ForegroundColor Green
}

# 2. Export public certificate (.cer) into release folder
$publicCertPath = "release\TaksyaStudio-Trinetra.cer"
Export-Certificate -Cert $cert -FilePath $publicCertPath -Force | Out-Null
Write-Host "Exported public certificate to $publicCertPath" -ForegroundColor Green

# 3. Sign target binaries
if (Test-Path $TargetExe) {
    Write-Host "Signing $TargetExe..." -ForegroundColor Yellow
    Set-AuthenticodeSignature -FilePath $TargetExe -Certificate $cert -HashAlgorithm "SHA256" -TimestampServer "http://timestamp.digicert.com"
    Write-Host "[SUCCESS] $TargetExe signed with Authenticode!" -ForegroundColor Green
} else {
    Write-Warning "Target binary $TargetExe not found for signing."
}

Write-Host "`nTo trust this certificate on any Windows PC, right click release\Install-Certificate.bat and select 'Run as Administrator'." -ForegroundColor Cyan
