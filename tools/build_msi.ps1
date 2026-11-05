<#
  Builds the MSI of Windows Maintenance Manager with the WiX Toolset (v4 or v5: dotnet tool install --global wix).
  Usage:  .\tools\build_msi.ps1 [-Sign -CertThumbprint <thumbprint>] [-OutDir release]
  In CI (2.11) the certificate comes from WMM_SIGN_PFX / WMM_SIGN_PASSWORD, like tools\build_installer.ps1.
  Output: dist\WindowsMaintenanceManager-<version>.msi
#>
param([switch]$Sign, [string]$CertThumbprint = "", [string]$OutDir = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$version = (Select-String -Path "$root\wmm\__init__.py" -Pattern 'VERSION = "([\d.]+)"').Matches[0].Groups[1].Value
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) { throw "WiX is not installed: dotnet tool install --global wix" }

$stage = Join-Path $env:TEMP "wmm-msi-$version"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
# Only the program: no data, tests, caches or git history.
robocopy $root $stage /E /XD .git .github .claude dati tests __pycache__ dist packaging tools .remember /XF *.pyc *.log | Out-Null

# Harvest the files into a component group (one component per file, stable GUIDs from the path).
$files = Get-ChildItem $stage -Recurse -File
$xml = New-Object System.Text.StringBuilder
[void]$xml.AppendLine('<?xml version="1.0" encoding="UTF-8"?><Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"><Fragment><ComponentGroup Id="WmmFiles" Directory="INSTALLFOLDER">')
foreach ($f in $files) {
  $rel = $f.FullName.Substring($stage.Length + 1)
  $sub = Split-Path $rel -Parent
  $md5 = [BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($rel))).Replace("-", "")
  $guid = "{0}-{1}-{2}-{3}-{4}" -f $md5.Substring(0, 8), $md5.Substring(8, 4), $md5.Substring(12, 4), $md5.Substring(16, 4), $md5.Substring(20, 12)
  $subdir = if ($sub) { " Subdirectory=`"$sub`"" } else { "" }
  [void]$xml.AppendLine("<Component Guid=`"$guid`"$subdir><File Source=`"$($f.FullName)`" /></Component>")
}
[void]$xml.AppendLine('</ComponentGroup></Fragment></Wix>')
Set-Content -Path "$stage\WmmFiles.wxs" -Value $xml.ToString() -Encoding UTF8

$dest = if ($OutDir) { $OutDir } else { "$root\dist" }
New-Item -ItemType Directory $dest -Force | Out-Null
$out = Join-Path (Resolve-Path $dest) "WindowsMaintenanceManager-$version.msi"
wix build "$root\packaging\wmm.wxs" "$stage\WmmFiles.wxs" -d Version=$version -arch x64 -o $out
if ($LASTEXITCODE -ne 0) { throw "wix build failed" }
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue | ForEach-Object Source
if (-not $signtool) {
  $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if ($Sign) {
  if (-not $CertThumbprint) { throw "-Sign needs -CertThumbprint" }
  & $signtool sign /sha1 $CertThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $out
  if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
} elseif ($env:WMM_SIGN_PFX) {
  if (-not $signtool) { throw "A signing certificate is set but signtool.exe (Windows SDK) was not found." }
  & $signtool sign /f $env:WMM_SIGN_PFX /p $env:WMM_SIGN_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /d "Windows Maintenance Manager" $out
  if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
} else {
  Write-Warning "No signing certificate: the MSI is NOT signed."
}
Write-Host "Built $out"
