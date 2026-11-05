<#
  Builds the MSI of Windows Maintenance Manager with the WiX Toolset (v4 or v5: dotnet tool install --global wix).
  Usage:  .\tools\build_msi.ps1 [-Sign -CertThumbprint <thumbprint>]
  Output: dist\WindowsMaintenanceManager-<version>.msi
#>
param([switch]$Sign, [string]$CertThumbprint = "")
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

New-Item -ItemType Directory "$root\dist" -Force | Out-Null
$out = "$root\dist\WindowsMaintenanceManager-$version.msi"
wix build "$root\packaging\wmm.wxs" "$stage\WmmFiles.wxs" -d Version=$version -arch x64 -o $out
if ($LASTEXITCODE -ne 0) { throw "wix build failed" }
if ($Sign) {
  if (-not $CertThumbprint) { throw "-Sign needs -CertThumbprint" }
  signtool sign /sha1 $CertThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $out
  if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
}
Write-Host "Built $out"
