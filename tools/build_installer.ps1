<#
  Builds the signed setup of Windows Maintenance Manager from the release zip (tools/build_release.py), then the winget
  manifests. Used by .github/workflows/release.yml; it also runs by hand:

    python tools/build_release.py release
    powershell -File tools/build_installer.ps1 -Release release [-BaseUrl https://github.com/mrbot0/WMMS/releases/download/v2.6.0]

  Signing (optional): the setup and its uninstaller are signed when one of these is set
    WMM_SIGN_PFX        path of a .pfx code-signing certificate, with WMM_SIGN_PASSWORD
    WMM_SIGN_THUMBPRINT thumbprint of a certificate in the current user's store (also hardware tokens)
  Without them the setup is built unsigned and a warning says so.
#>
param(
    [string]$Release = "release",
    [string]$BaseUrl = "",
    [string]$Timestamp = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$release = (Resolve-Path (Join-Path $root $Release)).Path
$version = (& python -c "import sys; sys.path.insert(0, r'$root'); import wmm; print(wmm.VERSION)").Trim()
$zip = Join-Path $release "WindowsMaintenanceManager-$version.zip"
if (-not (Test-Path $zip)) { throw "Missing ${zip}: run python tools/build_release.py first." }

# The setup packs exactly what the in-app updater ships.
$staging = Join-Path $release "staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
Expand-Archive $zip -DestinationPath $staging
$source = Join-Path $staging "WindowsMaintenanceManager"

$iscc = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue | ForEach-Object Source),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 was not found: winget install JRSoftware.InnoSetup (or choco install innosetup)." }

function Find-SignTool {
    $found = Get-Command signtool.exe -ErrorAction SilentlyContinue | ForEach-Object Source
    if ($found) { return $found }
    Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}

$arguments = @("/Q", "/DAppVersion=$version", "/DSourceDir=$source", "/DOutputDir=$release")
$signed = $false
if ($env:WMM_SIGN_PFX -or $env:WMM_SIGN_THUMBPRINT) {
    $signtool = Find-SignTool
    if (-not $signtool) { throw "A signing certificate is set but signtool.exe (Windows SDK) was not found." }
    if ($env:WMM_SIGN_PFX) {
        $who = "/f `$q$($env:WMM_SIGN_PFX)`$q /p `$q$($env:WMM_SIGN_PASSWORD)`$q"
    } else {
        $who = "/sha1 $($env:WMM_SIGN_THUMBPRINT)"
    }
    # Inno Setup calls this for the setup and for the uninstaller it embeds; $q is a quote and $f the file.
    $arguments += "/DSignToolCmd"
    $arguments += "/Swmmsign=`$q$signtool`$q sign /fd sha256 /tr $Timestamp /td sha256 $who /d `$qWindows Maintenance Manager`$q `$f"
    $signed = $true
}
& $iscc @arguments (Join-Path $root "packaging\WindowsMaintenanceManager.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$setup = Join-Path $release "WindowsMaintenanceManager-Setup-$version.exe"
if ($signed) {
    $signature = Get-AuthenticodeSignature $setup
    if ($signature.Status -ne "Valid") { throw "The setup signature is not valid: $($signature.Status) $($signature.StatusMessage)" }
    Write-Host "Signed by $($signature.SignerCertificate.Subject)"
} else {
    Write-Warning "No signing certificate (WMM_SIGN_PFX or WMM_SIGN_THUMBPRINT): the setup is NOT signed and SmartScreen will warn."
}

$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
Add-Content -Path (Join-Path $release "SHA256SUMS.txt") -Value "$hash  $(Split-Path -Leaf $setup)" -Encoding ascii
Remove-Item $staging -Recurse -Force

if (-not $BaseUrl) { $BaseUrl = "https://github.com/mrbot0/WMMS/releases/download/v$version" }
& python (Join-Path $root "tools\winget_manifest.py") --version $version --url "$BaseUrl/$(Split-Path -Leaf $setup)" --sha256 $hash --out (Join-Path $release "winget")
if ($LASTEXITCODE -ne 0) { throw "The winget manifests could not be written." }
Write-Host "Setup: $setup"
