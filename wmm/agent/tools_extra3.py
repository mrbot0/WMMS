"""Thirty more toolbox fixes (iteration 14): the repairs technicians reach for when something everyday stops working
(no internet warning, Start menu, camera, Windows Hello, typing, notifications, Office, Windows Installer, restore
points), plus the settings people ask for most and the cleanups that free gigabytes. Every fix goes through ctx.comando,
so preview mode simulates it. Every script is plain ASCII (it travels base64-encoded)."""
from __future__ import annotations

from .tools_extra import ps  # noqa: F401  (fixes use the same preview-aware runner)

# Winlogon restarts the shell by itself (AutoRestartShell), unelevated as before.
_RESTART_EXPLORER = "Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force\n"

# ---------- network ----------

SCRIPT_DISCOVERY_ON = r"""
# The services that make this PC visible and let it see the others.
Set-Service FDResPub -StartupType Automatic -ErrorAction SilentlyContinue
foreach ($s in 'fdPHost', 'SSDPSRV', 'upnphost') { Set-Service $s -StartupType Manual -ErrorAction SilentlyContinue }
foreach ($s in 'fdPHost', 'FDResPub', 'SSDPSRV', 'upnphost', 'LanmanServer', 'LanmanWorkstation') { Start-Service $s -ErrorAction SilentlyContinue }
# Firewall groups by their resource names: the display names are translated. Only the Private profile is opened.
$groups = '@FirewallAPI.dll,-32752', '@FirewallAPI.dll,-28502'
$rules = Get-NetFirewallRule -Group $groups -ErrorAction SilentlyContinue | Where-Object { $_.Profile.ToString() -match 'Private' }
$rules | Enable-NetFirewallRule
"Network discovery and file and printer sharing are on for Private networks ($(@($rules).Count) firewall rules)."
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory | Format-Table -AutoSize | Out-String
if (Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public') { 'A network above is Public: mark it Private (Toolbox: Mark the current network as private) to be seen on it.' }
"""

SCRIPT_PROFILE_PRIVATE = r"""
$p = Get-NetConnectionProfile -ErrorAction SilentlyContinue
if (-not $p) { 'No connected network.'; exit 0 }
foreach ($n in $p) {
  if ($n.NetworkCategory -eq 'DomainAuthenticated') { "$($n.Name) ($($n.InterfaceAlias)): company domain network, left as it is."; continue }
  if ($n.NetworkCategory -eq 'Private') { "$($n.Name) ($($n.InterfaceAlias)): already Private."; continue }
  Set-NetConnectionProfile -InterfaceIndex $n.InterfaceIndex -NetworkCategory Private
  "$($n.Name) ($($n.InterfaceAlias)): now Private."
}
'Private lets PCs, printers and media players on this network see each other. On public Wi-Fi (bars, hotels, stations) keep it Public.'
"""

SCRIPT_NCSI_RESET = r"""
# The connectivity test behind the "No internet" globe in the taskbar, back to the Microsoft defaults.
$k = 'HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet'
if (-not (Test-Path $k)) { New-Item $k -Force | Out-Null }
$v = [ordered]@{ ActiveWebProbeHost = 'www.msftconnecttest.com'; ActiveWebProbePath = 'connecttest.txt'; ActiveWebProbeContent = 'Microsoft Connect Test';
  ActiveWebProbeHostV6 = 'ipv6.msftconnecttest.com'; ActiveWebProbePathV6 = 'connecttest.txt'; ActiveWebProbeContentV6 = 'Microsoft Connect Test';
  ActiveDnsProbeHost = 'dns.msftncsi.com'; ActiveDnsProbeContent = '131.107.255.255'; ActiveDnsProbeHostV6 = 'dns.msftncsi.com'; ActiveDnsProbeContentV6 = 'fd3e:4f5a:5b81::1' }
foreach ($n in $v.Keys) { Set-ItemProperty $k -Name $n -Value $v[$n] }
Set-ItemProperty $k -Name EnableActiveProbing -Value 1 -Type DWord
# Tweaking tools often turn the test off through a policy: then Windows always says "No internet".
Remove-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\NetworkConnectivityStatusIndicator' -Name NoActiveProbe, DisablePassivePolling, UseGlobalDNS -ErrorAction SilentlyContinue
# Windows 11 24H2 and later run the test in the Network List Service; earlier builds in NlaSvc.
if ((Get-Service NlaSvc -ErrorAction SilentlyContinue).Status -eq 'Running') { Restart-Service NlaSvc -Force -ErrorAction SilentlyContinue }
else { Restart-Service netprofm -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 6
'Internet connectivity test reset; the network status now:'
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, IPv4Connectivity, IPv6Connectivity | Format-Table -AutoSize | Out-String
"""

# ---------- updates ----------

SCRIPT_BITS_RESET = r"""
Start-Service BITS -ErrorAction SilentlyContinue
$jobs = @(Get-BitsTransfer -AllUsers -ErrorAction SilentlyContinue)
$jobs | Remove-BitsTransfer -ErrorAction SilentlyContinue
Stop-Service BITS -Force -ErrorAction SilentlyContinue
# The queue database: a damaged one keeps every download (updates, Store, Defender) stuck at 0%.
Get-ChildItem "$env:ALLUSERSPROFILE\Microsoft\Network\Downloader" -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^qmgr' } | Remove-Item -Force -ErrorAction SilentlyContinue
sc.exe config BITS start= delayed-auto | Out-Null
Start-Service BITS -ErrorAction SilentlyContinue
"Background downloads (BITS) repaired: $($jobs.Count) stuck transfers removed, queue rebuilt. Windows Update starts the downloads again."
(Get-Service BITS | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String)
"""

SCRIPT_REMOVE_WU_POLICIES = r"""
if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) { 'This PC belongs to a company domain: its update policies come from IT, so nothing was changed.'; exit 1 }
$k = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
if (-not (Test-Path $k)) { 'No Windows Update policy is set: nothing to remove.'; exit 0 }
'Update policies found:'
foreach ($p in $k, "$k\AU") {
  $i = Get-ItemProperty $p -ErrorAction SilentlyContinue
  if ($i) { $i.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object { "  $($_.Name) = $($_.Value)" } }
}
$dir = Join-Path $env:ProgramData 'WMM'
New-Item -ItemType Directory $dir -Force | Out-Null
$backup = Join-Path $dir ("wu-policies-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.reg')
reg export 'HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate' $backup /y | Out-Null
Remove-Item $k -Recurse -Force
Restart-Service wuauserv -Force -ErrorAction SilentlyContinue
''; 'Removed: Windows Update follows its normal settings again (no WSUS server, no blocked or deferred updates).'
"Backup: $backup (double-click it to put the policies back)."
"""

SCRIPT_MICROSOFT_UPDATE_ON = r"""
$sm = New-Object -ComObject Microsoft.Update.ServiceManager
$id = '7971f918-a847-4430-9279-4a52d1efe18d'
if ($sm.Services | Where-Object { $_.ServiceID -eq $id }) { 'Microsoft Update is already on.'; exit 0 }
$sm.AddService2($id, 7, '') | Out-Null
'Microsoft Update is on: Windows Update now also brings the fixes for Office (MSI), .NET, SQL Server, Visual C++ and other Microsoft products.'
"""

# ---------- startup and apps ----------

SCRIPT_REREGISTER_APPS = r"""
# The apps that are part of Windows (Start, Settings, search, Windows Security, Store): registering them again fixes
# "nothing happens when I click Start or Settings". Apps from the Store are left alone.
$pk = Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | Where-Object { $_.SignatureKind -eq 'System' -and $_.InstallLocation }
if (-not $pk) { $pk = Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { $_.SignatureKind -eq 'System' -and $_.InstallLocation } }
if (-not $pk) { 'The list of Windows apps cannot be read (administrator rights needed).'; exit 1 }
$ok = 0; $ko = 0
foreach ($p in $pk) {
  $m = Join-Path $p.InstallLocation 'AppxManifest.xml'
  if (-not (Test-Path $m)) { continue }
  try { Add-AppxPackage -DisableDevelopmentMode -Register $m -ErrorAction Stop; $ok++ } catch { $ko++ }
}
"$ok built-in apps registered again" + $(if ($ko) { "; $ko skipped (in use or not for this account, which is normal)" })
'If Start or Settings still do not open, restart the PC.'
"""

SCRIPT_RESET_START_MENU = r"""
$names = 'StartMenuExperienceHost', 'ShellExperienceHost', 'SearchHost', 'SearchApp', 'TextInputHost'
$p = Get-Process $names -ErrorAction SilentlyContinue
$p | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
"Start menu, search and the taskbar panels restarted ($(@($p).Count) processes): Windows opens them again on the next click."
"""

SCRIPT_RESET_NOTIFICATIONS = r"""
$dir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Notifications'
if (-not (Test-Path (Join-Path $dir 'wpndatabase.db'))) { 'The notification database was not found for this account.'; exit 0 }
$svc = Get-Service 'WpnUserService_*' -ErrorAction SilentlyContinue
$svc | Stop-Service -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Remove-Item (Join-Path $dir 'wpndatabase.db-shm'), (Join-Path $dir 'wpndatabase.db-wal') -Force -ErrorAction SilentlyContinue
Rename-Item (Join-Path $dir 'wpndatabase.db') "wpndatabase.db.old-$stamp" -ErrorAction Stop
$svc | Start-Service -ErrorAction SilentlyContinue
Restart-Service WpnService -Force -ErrorAction SilentlyContinue
'Notification database rebuilt: banners, the notification center and the badges work again.'
'Old notifications are gone; apps may ask once more to show notifications.'
"""

SCRIPT_OFFICE_QUICK_REPAIR = r"""
$c2r = Join-Path $env:CommonProgramFiles 'Microsoft Shared\ClickToRun\OfficeClickToRun.exe'
if (-not (Test-Path $c2r)) { 'Microsoft 365 / Office (Click-to-Run) is not installed. An older MSI Office is repaired from Settings > Apps.'; exit 0 }
$cfg = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration' -ErrorAction SilentlyContinue
$platform = if ($cfg.Platform) { $cfg.Platform } else { 'x64' }
$culture = if ($cfg.ClientCulture) { $cfg.ClientCulture } else { 'en-us' }
"Office: $($cfg.ProductReleaseIds) $($cfg.VersionToReport) ($platform, $culture)"
Start-Process $c2r -ArgumentList "scenario=Repair platform=$platform culture=$culture RepairType=QuickRepair forceappshutdown=True DisplayLevel=False" -Wait
'Quick repair finished: damaged Office files were replaced from the local copy, without downloading Office again.'
'If Word, Excel or Outlook still crash, run the Online repair from Settings > Apps > Microsoft 365 > Modify.'
"""

# ---------- services ----------

SCRIPT_RESTART_CAMERA = r"""
$deny = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam' -ErrorAction SilentlyContinue).Value
foreach ($s in 'FrameServer', 'FrameServerMonitor') { Restart-Service $s -Force -ErrorAction SilentlyContinue }
$cams = @(Get-PnpDevice -Class Camera, Image -PresentOnly -ErrorAction SilentlyContinue)
if (-not $cams) { 'No camera found: check the cable, the privacy shutter or the camera key (often F8 or F10) and the BIOS.'; exit 1 }
foreach ($c in $cams) { "Restarting $($c.FriendlyName) ($($c.Status))..."; pnputil /restart-device "$($c.InstanceId)" | Out-Null }
'Camera service and camera restarted. Close and reopen the app that uses it.'
if ($deny -eq 'Deny') { ''; 'Camera access is turned OFF in Settings > Privacy & security > Camera: apps cannot use it until you turn it on.'; exit 1 }
"""

SCRIPT_RESTART_BIOMETRICS = r"""
if (-not (Get-Service WbioSrvc -ErrorAction SilentlyContinue)) { 'The Windows Biometric Service is missing on this PC.'; exit 1 }
Restart-Service WbioSrvc -Force -ErrorAction SilentlyContinue
$dev = @(Get-PnpDevice -Class Biometric -PresentOnly -ErrorAction SilentlyContinue)
foreach ($d in $dev) { "Restarting $($d.FriendlyName)..."; pnputil /restart-device "$($d.InstanceId)" | Out-Null }
if (-not $dev) { 'No fingerprint reader or face camera found.' }
'Windows Hello restarted. If face or fingerprint sign-in still fails, set it up again in Settings > Accounts > Sign-in options.'
"""

SCRIPT_RESTART_TEXT_INPUT = r"""
# ctfmon serves the keyboard to modern apps: when it stops you cannot type in Start, search, Settings or the Store.
Get-Process ctfmon, TextInputHost -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Restart-Service TextInputManagementService -Force -ErrorAction SilentlyContinue
$t = Get-ScheduledTask -TaskPath '\Microsoft\Windows\TextServicesFramework\' -TaskName 'MsCtfMonitor' -ErrorAction SilentlyContinue
if ($t) { $t | Enable-ScheduledTask | Out-Null; Start-ScheduledTask -TaskPath '\Microsoft\Windows\TextServicesFramework\' -TaskName 'MsCtfMonitor' }
Start-Sleep -Seconds 2
if (Get-Process ctfmon -ErrorAction SilentlyContinue) { 'Typing restored: the text input service (ctfmon) is running again.' }
else { 'The text input service did not start: sign out and back in, then try again.'; exit 1 }
"""

# ---------- integrity ----------

SCRIPT_RESET_GROUP_POLICY = r"""
if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) { 'This PC belongs to a company domain: its policies come from IT, so nothing was changed.'; exit 1 }
$dirs = "$env:WinDir\System32\GroupPolicy", "$env:WinDir\System32\GroupPolicyUsers" | Where-Object { Test-Path $_ }
if (-not $dirs) { 'No local Group Policy is set: nothing to reset.'; exit 0 }
$backup = Join-Path $env:ProgramData ("WMM\group-policy-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory $backup -Force | Out-Null
foreach ($d in $dirs) { Copy-Item $d $backup -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item $d -Recurse -Force }
gpupdate /force | Out-Null
'Local Group Policy reset: settings blocked by tweaking or "privacy" tools are free again ("Some settings are managed by your organization" goes away).'
"Backup: $backup"
'Restart the PC to finish.'
"""

SCRIPT_REREGISTER_MSI = r"""
Stop-Service msiserver -Force -ErrorAction SilentlyContinue
foreach ($exe in "$env:WinDir\System32\msiexec.exe", "$env:WinDir\SysWOW64\msiexec.exe") {
  if (Test-Path $exe) { Start-Process $exe '/unregister' -Wait -WindowStyle Hidden; Start-Process $exe '/regserver' -Wait -WindowStyle Hidden }
}
Set-Service msiserver -StartupType Manual
Start-Service msiserver -ErrorAction SilentlyContinue
"Windows Installer registered again ($((Get-Service msiserver).Status)): installs and uninstalls that failed with 'The Windows Installer service could not be accessed' can be tried again."
"""

SCRIPT_RESTART_VSS = r"""
foreach ($s in 'VSS', 'swprv') { Set-Service $s -StartupType Manual -ErrorAction SilentlyContinue; Stop-Service $s -Force -ErrorAction SilentlyContinue }
Start-Service swprv, VSS -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$w = vssadmin list writers | Out-String
# The state numbers are the same in every language: 1 is stable, 6 to 15 are failures.
$failed = ([regex]::Matches($w, '\[(?:[6-9]|1[0-5])\]')).Count
$all = ([regex]::Matches($w, '\[\d+\]')).Count
if (-not $all) { 'Shadow copy services restarted, but their writers cannot be listed (administrator rights needed).'; exit 1 }
"Shadow copy services restarted: $all writers, $failed failed."
if ($failed) { ''; $w; 'Some writers are still failed: restart the PC, then create the restore point or the backup again.'; exit 1 }
'Restore points and backups (File History, image backups) can run again.'
"""

SCRIPT_SECURITY_APP_RESET = r"""
$p = Get-AppxPackage Microsoft.SecHealthUI -ErrorAction SilentlyContinue
if (-not $p) { $p = Get-AppxPackage -AllUsers Microsoft.SecHealthUI -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (-not $p) { 'The Windows Security app is not installed: run System File Checker and DISM from Integrity.'; exit 1 }
try { $p | Reset-AppxPackage -ErrorAction Stop } catch { Add-AppxPackage -DisableDevelopmentMode -Register (Join-Path $p.InstallLocation 'AppxManifest.xml') }
Restart-Service SecurityHealthService -Force -ErrorAction SilentlyContinue
"Windows Security app repaired ($($p.Version)): it opens again from Start or the shield in the taskbar."
"""

# ---------- security ----------

SCRIPT_SHOW_EXTENSIONS = r"""
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' -Name HideFileExt -Value 0 -Type DWord
'File extensions are visible: "invoice.pdf.exe" can no longer pass for a PDF. Open folders show them after F5.'
"""

SCRIPT_REMOTE_ASSISTANCE_OFF = r"""
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance' -Name fAllowToGetHelp -Value 0 -Type DWord
Get-NetFirewallRule -Group '@FirewallAPI.dll,-33002' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
'Remote Assistance is off: nobody can be invited to take control of this PC, a trick used by phone scammers.'
'Quick Assist and remote desktop apps you install yourself still work.'
"""

# ---------- performance and Explorer ----------

SCRIPT_FOLDER_VIEWS_RESET = r"""
foreach ($k in 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags', 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU',
               'HKCU:\Software\Microsoft\Windows\Shell\Bags', 'HKCU:\Software\Microsoft\Windows\Shell\BagMRU') {
  Remove-Item $k -Recurse -Force -ErrorAction SilentlyContinue
}
""" + _RESTART_EXPLORER + r"""
'Folder views reset: every folder opens with the default layout, and folders that were slow or showed the wrong columns are fixed.'
"""

SCRIPT_FOLDER_TYPE_OFF = r"""
$k = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell'
New-Item $k -Force | Out-Null
Set-ItemProperty $k -Name FolderType -Value 'NotSpecified'
""" + _RESTART_EXPLORER + r"""
'Folders no longer guess their content: Downloads and other big folders open at once instead of "Working on it...".'
'Folder views reset brings the automatic guessing back.'
"""

SCRIPT_CLASSIC_CONTEXT_MENU = r"""
if ([Environment]::OSVersion.Version.Build -lt 22000) { 'This is Windows 10: the right-click menu is already the full one.'; exit 0 }
$k = 'HKCU:\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32'
New-Item $k -Force | Out-Null
Set-ItemProperty $k -Name '(default)' -Value ''
""" + _RESTART_EXPLORER + r"""
'The right-click menu opens the full list at once, without "Show more options".'
"""

SCRIPT_CONTEXT_MENU_DEFAULT = r"""
Remove-Item 'HKCU:\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}' -Recurse -Force -ErrorAction SilentlyContinue
""" + _RESTART_EXPLORER + r"""
'The Windows 11 right-click menu is back (the full list stays under "Show more options").'
"""

SCRIPT_WEB_SEARCH_OFF = r"""
$s = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search'
New-Item $s -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty $s -Name BingSearchEnabled -Value 0 -Type DWord
Set-ItemProperty $s -Name CortanaConsent -Value 0 -Type DWord
$p = 'HKCU:\Software\Policies\Microsoft\Windows\Explorer'
New-Item $p -Force -ErrorAction SilentlyContinue | Out-Null
Set-ItemProperty $p -Name DisableSearchBoxSuggestions -Value 1 -Type DWord
Get-Process SearchHost, SearchApp -ErrorAction SilentlyContinue | Stop-Process -Force
'Start search shows only your apps, files and settings: no Bing results, faster and nothing typed leaves the PC.'
"""

SCRIPT_MPO_OFF = r"""
Set-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\Dwm' -Name OverlayTestMode -Value 5 -Type DWord
'Multiplane overlay (MPO) turned off. Restart the PC: it cures flicker, black flashes and stutter in browsers and games on many NVIDIA and AMD cards.'
'If nothing changes, use "Screen overlays back to default".'
"""

SCRIPT_MPO_DEFAULT = r"""
Remove-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\Dwm' -Name OverlayTestMode -ErrorAction SilentlyContinue
'Multiplane overlay back to the Windows default. Restart the PC to apply.'
"""

SCRIPT_END_TASK_ON = r"""
if ([Environment]::OSVersion.Version.Build -lt 22631) { 'End task in the taskbar needs Windows 11 23H2 or later.'; exit 1 }
$k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings'
New-Item $k -Force | Out-Null
Set-ItemProperty $k -Name TaskbarEndTask -Value 1 -Type DWord
'Right-click a frozen app in the taskbar and choose "End task": no Task Manager needed.'
"""

# ---------- cleanup ----------

SCRIPT_UPGRADE_LEFTOVERS = r"""
if (Get-Process SetupHost, SetupPrep, Windows10UpgraderApp -ErrorAction SilentlyContinue) { 'A Windows upgrade is running right now: try again when it has finished.'; exit 1 }
$d = $env:SystemDrive
$paths = "$d\`$WINDOWS.~BT", "$d\`$Windows.~WS", "$d\`$GetCurrent", "$d\`$WinREAgent", "$d\ESD", "$d\Windows10Upgrade" | Where-Object { Test-Path -LiteralPath $_ }
if (-not $paths) { 'No leftovers of Windows upgrades or the Media Creation Tool.'; exit 0 }
$total = 0
foreach ($p in $paths) {
  $size = (Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  # Administrators by SID: the group name is translated.
  icacls $p /grant '*S-1-5-32-544:F' /T /C /Q | Out-Null
  Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
  $state = if (Test-Path -LiteralPath $p) { 'partly removed (files in use)' } else { 'removed' }
  '{0}: {1:N2} GB {2}' -f $p, ($size / 1GB), $state
  if (-not (Test-Path -LiteralPath $p)) { $total += $size }
}
''; 'Freed: {0:N2} GB. Windows.old (the previous Windows) is not touched: Storage > Remove Windows.old does that.' -f ($total / 1GB)
"""

SCRIPT_GPU_INSTALLER_LEFTOVERS = r"""
$d = $env:SystemDrive
$paths = @("$d\NVIDIA", "$d\AMD") + @(Get-ChildItem "$env:ProgramData\NVIDIA Corporation\Downloader" -Directory -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -ne 'latest' } | ForEach-Object FullName) | Where-Object { Test-Path -LiteralPath $_ }
if (-not $paths) { 'No graphics driver installers left behind.'; exit 0 }
$total = 0
foreach ($p in $paths) {
  $size = (Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
  if (-not (Test-Path -LiteralPath $p)) { $total += $size; '{0}: {1:N2} GB removed' -f $p, ($size / 1GB) } else { "$p could not be removed (in use)" }
}
''; 'Freed: {0:N2} GB of unpacked NVIDIA and AMD driver installers. The installed drivers are not touched.' -f ($total / 1GB)
"""

SCRIPT_OLD_DRIVER_PACKAGES = r"""
$all = Get-WindowsDriver -Online -ErrorAction Stop
# The same driver in several versions: keep the newest, try to delete the others. pnputil refuses (without /force)
# any package a device still uses, so nothing in use can go.
$groups = $all | Group-Object { (Split-Path $_.OriginalFileName -Leaf) + '|' + $_.ProviderName + '|' + $_.ClassName } | Where-Object Count -gt 1
if (-not $groups) { 'No old driver versions in the driver store.'; exit 0 }
$freed = 0; $removed = 0; $kept = 0
foreach ($g in $groups) {
  $sorted = $g.Group | Sort-Object Date, { [version]($_.Version -replace '[^\d.]', '') } -Descending
  foreach ($old in ($sorted | Select-Object -Skip 1)) {
    $dir = Split-Path $old.OriginalFileName -Parent
    $size = (Get-ChildItem -LiteralPath $dir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    pnputil /delete-driver $old.Driver | Out-Null
    if ($LASTEXITCODE -eq 0) { $removed++; $freed += $size; "Removed $($old.ProviderName) $($old.ClassName) $($old.Version) ($($old.Driver))" } else { $kept++ }
  }
}
''; "Old driver packages removed: $removed; kept because a device uses them: $kept. Freed: {0:N0} MB." -f ($freed / 1MB)
"""
