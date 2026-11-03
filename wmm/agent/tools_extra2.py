"""Forty more toolbox tools (iteration 13): fixes for problems technicians meet every week and read-only checks that
answer "why is this PC slow, insecure or out of date?". Reports exit with 1 when they find something worth a look;
fixes go through ctx.comando, so preview mode simulates them. Every script is plain ASCII (it travels base64-encoded)."""
from __future__ import annotations

from .tools_extra import ps  # noqa: F401  (fixes use the same preview-aware runner)

# ---------- fixes ----------

SCRIPT_RESET_TCPIP = r"""
netsh int ip reset | Out-String
netsh int ipv6 reset | Out-String
'TCP/IP stack reset to its defaults. Restart the PC to finish: static IP addresses must be set again afterwards.'
"""

SCRIPT_RESTART_ADAPTERS = r"""
$a = Get-NetAdapter -Physical | Where-Object Status -ne 'Disabled'
if (-not $a) { 'No physical network adapter to restart.'; exit 0 }
foreach ($n in $a) { "Restarting $($n.Name) ($($n.InterfaceDescription))..."; Restart-NetAdapter -Name $n.Name -Confirm:$false }
Start-Sleep -Seconds 8
Get-NetAdapter -Physical | Select-Object Name, Status, LinkSpeed | Format-Table -AutoSize | Out-String
"""

SCRIPT_PREFER_IPV4 = r"""
New-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Name DisabledComponents -Value 0x20 -PropertyType DWord -Force | Out-Null
'IPv4 is now preferred over IPv6 (IPv6 stays on). Restart the PC to apply. Use it when sites load slowly or fail only on IPv6.'
"""

SCRIPT_IPV6_DEFAULT = r"""
Remove-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Name DisabledComponents -ErrorAction SilentlyContinue
'IPv6 back to the Windows default. Restart the PC to apply.'
"""

SCRIPT_REBUILD_PERF_COUNTERS = r"""
Set-Location "$env:SystemRoot\System32"; lodctr /R | Out-String
Set-Location "$env:SystemRoot\SysWOW64"; lodctr /R | Out-String
winmgmt /resyncperf | Out-String
'Performance counters rebuilt: Task Manager, Resource Monitor and the live figures of this console read them again.'
"""

SCRIPT_RESET_POWER_PLANS = r"""
powercfg -restoredefaultschemes
powercfg /list
'Power plans back to the Windows defaults (custom plans are removed).'
"""

SCRIPT_REBUILD_SEARCH = r"""
Stop-Service WSearch -Force -ErrorAction SilentlyContinue
Set-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Search' -Name SetupCompletedSuccessfully -Value 0 -Type DWord
Start-Service WSearch
'Windows Search index reset: it rebuilds in the background. Search results come back fully in an hour or two.'
"""

SCRIPT_WINGET_SOURCE_RESET = r"""
$w = Get-Command winget -ErrorAction SilentlyContinue
if (-not $w) { 'winget is not installed: install App Installer from the Microsoft Store.'; exit 1 }
winget source reset --force --disable-interactivity | Out-String
winget source update --disable-interactivity | Out-String
'winget sources reset and updated: app updates and installs work again.'
"""

SCRIPT_RESETBASE = r"""
Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase
"""

SCRIPT_VERIFIER_OFF = r"""
verifier /reset | Out-String
'Driver Verifier turned off. Restart the PC: it slowed every driver down and can cause blue screens on purpose.'
"""

SCRIPT_PS_POLICY = r"""
Set-ExecutionPolicy RemoteSigned -Scope LocalMachine -Force
Get-ExecutionPolicy -List | Format-Table -AutoSize | Out-String
'PowerShell runs local scripts, but downloaded scripts must be signed (RemoteSigned).'
"""

# ---------- network reports ----------

SCRIPT_DNS_BENCHMARK = r"""
$names = 'www.microsoft.com', 'www.google.com', 'www.wikipedia.org', 'www.amazon.com', 'www.cloudflare.com'
$servers = [ordered]@{ 'Current (this PC)' = $null; 'Cloudflare 1.1.1.1' = '1.1.1.1'; 'Google 8.8.8.8' = '8.8.8.8'; 'Quad9 9.9.9.9' = '9.9.9.9' }
$rows = foreach ($k in $servers.Keys) {
  $times = foreach ($n in $names) {
    Clear-DnsClientCache
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { if ($servers[$k]) { Resolve-DnsName $n -Server $servers[$k] -DnsOnly -ErrorAction Stop | Out-Null } else { Resolve-DnsName $n -DnsOnly -ErrorAction Stop | Out-Null }; $sw.Elapsed.TotalMilliseconds }
    catch { 9999 }
  }
  [pscustomobject]@{ Server = $k; 'Average ms' = [math]::Round(($times | Measure-Object -Average).Average); 'Worst ms' = [math]::Round(($times | Measure-Object -Maximum).Maximum) }
}
'DNS response time (5 sites, cache cleared before each lookup):'
$rows | Sort-Object 'Average ms' | Format-Table -AutoSize | Out-String
$cur = ($rows | Where-Object Server -like 'Current*').'Average ms'; $best = ($rows | Measure-Object 'Average ms' -Minimum).Minimum
if ($cur -gt 2 * $best -and $cur -gt 60) { 'The DNS of this PC is much slower than a public one: set Cloudflare or Quad9 from the Network area.'; exit 1 }
"""

SCRIPT_WIFI_NETWORKS = r"""
$out = netsh wlan show networks mode=bssid
if ($out -match 'There is no wireless interface|service is not running') { 'No Wi-Fi adapter or WLAN service on this PC.'; exit 0 }
$cur = netsh wlan show interfaces
'Connected now:'; $cur | Select-String 'SSID|Channel|Signal|Radio type|Receive rate' | ForEach-Object { '  ' + $_.Line.Trim() }
''; 'Networks around (signal and channel): many networks on the same channel slow each other down.'
$out | Select-String '^SSID|Signal|Channel|Authentication' | ForEach-Object { '  ' + $_.Line.Trim() }
"""

SCRIPT_NIC_ERRORS = r"""
$s = Get-NetAdapterStatistics -ErrorAction SilentlyContinue
if (-not $s) { 'No adapter statistics available.'; exit 0 }
'Errors and discarded packets since the adapters started:'
$s | Select-Object Name, @{n='Received';e={$_.ReceivedUnicastPackets}}, @{n='Receive errors';e={$_.ReceivedPacketErrors}}, @{n='Receive discarded';e={$_.ReceivedDiscardedPackets}},
  @{n='Send errors';e={$_.OutboundPacketErrors}}, @{n='Send discarded';e={$_.OutboundDiscardedPackets}} | Format-Table -AutoSize | Out-String -Width 200
$bad = $s | Where-Object { $_.ReceivedPacketErrors -gt 100 -or $_.OutboundPacketErrors -gt 100 }
if ($bad) { 'Many errors: check the cable, the port, the switch or the Wi-Fi signal.'; exit 1 }
"""

SCRIPT_DHCP = r"""
Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = True' | ForEach-Object {
  "$($_.Description)"
  "  DHCP: " + $(if ($_.DHCPEnabled) { "yes, server $($_.DHCPServer)" } else { 'no (static address)' })
  if ($_.DHCPEnabled -and $_.DHCPLeaseExpires) { "  Lease obtained: $($_.DHCPLeaseObtained)   expires: $($_.DHCPLeaseExpires)" }
  "  Addresses: $($_.IPAddress -join ', ')   Gateway: $($_.DefaultIPGateway -join ', ')   DNS: $($_.DNSServerSearchOrder -join ', ')"
  ''
}
"""

SCRIPT_INTERNET_CONNECTIONS = r"""
$c = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object { $_.RemoteAddress -notmatch '^(127\.|::1|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|fe80)' }
if (-not $c) { 'No open connection to the internet right now.'; exit 0 }
'Programs talking to the internet right now:'
$c | Group-Object OwningProcess | ForEach-Object {
  $p = Get-Process -Id $_.Name -ErrorAction SilentlyContinue
  [pscustomobject]@{ Program = $(if ($p) { $p.ProcessName } else { "PID $($_.Name)" }); Connections = $_.Count; 'Remote addresses' = (($_.Group.RemoteAddress | Select-Object -Unique -First 4) -join ', '); Path = $(if ($p) { $p.Path } else { '' }) }
} | Sort-Object Connections -Descending | Format-Table -AutoSize | Out-String -Width 240
"""

SCRIPT_VPN_ADAPTERS = r"""
$v = Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceDescription -match 'TAP|TUN|WireGuard|VPN|Wintun|OpenVPN|Fortinet|AnyConnect|NordLynx|Hyper-V|VirtualBox|VMware|Loopback' }
if (-not $v) { 'No VPN or virtual network adapter.'; exit 0 }
'VPN and virtual network adapters (old VPNs left behind often break DNS or slow the network):'
$v | Select-Object Name, InterfaceDescription, Status | Format-Table -AutoSize | Out-String -Width 200
"""

SCRIPT_SHARE_SESSIONS = r"""
'Who is connected to the shared folders of this PC now:'
$s = Get-SmbSession -ErrorAction SilentlyContinue
if (-not $s) { '  nobody' } else { $s | Select-Object ClientComputerName, ClientUserName, NumOpens, SecondsExists | Format-Table -AutoSize | Out-String }
$f = Get-SmbOpenFile -ErrorAction SilentlyContinue
if ($f) { ''; "Files open from the network: $(@($f).Count)"; $f | Select-Object -First 20 ClientUserName, Path | Format-Table -AutoSize | Out-String -Width 200 }
"""

# ---------- security reports ----------

SCRIPT_SUSPICIOUS_TASKS = r"""
$bad = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object {
  $t = $_
  foreach ($a in $t.Actions) {
    $cmd = "$($a.Execute) $($a.Arguments)"
    if ($cmd -match '\\AppData\\|\\Temp\\|\\Users\\Public\\|-enc(odedcommand)?\s|FromBase64String|mshta|regsvr32.+/i:http|bitsadmin') {
      [pscustomobject]@{ Task = $t.TaskPath + $t.TaskName; Runs = $cmd.Substring(0, [math]::Min(140, $cmd.Length)) }
    }
  }
}
if (-not $bad) { 'No scheduled task runs programs from user folders or with encoded commands.'; exit 0 }
'Scheduled tasks that run from user or temporary folders, or with encoded commands (a common malware trick):'
$bad | Format-Table -AutoSize -Wrap | Out-String -Width 240
'Some are legitimate (updaters of user-installed apps): check the unknown ones.'
exit 1
"""

SCRIPT_UNQUOTED_SERVICES = r"""
$s = Get-CimInstance Win32_Service | Where-Object { $_.PathName -and $_.PathName -notmatch '^\s*"' -and $_.PathName -match '^[^"]*\s[^"]*\.exe' -and $_.PathName -notmatch '^[A-Za-z]:\\Windows\\' }
if (-not $s) { 'No service has an unquoted path with spaces.'; exit 0 }
'Services whose program path has spaces but no quotes (a known way to run a fake program with system rights):'
$s | Select-Object Name, StartMode, PathName | Format-Table -AutoSize -Wrap | Out-String -Width 240
exit 1
"""

SCRIPT_SERVICES_OUTSIDE = r"""
$s = Get-CimInstance Win32_Service | Where-Object { $_.PathName } | ForEach-Object {
  $p = ($_.PathName -replace '^\s*"([^"]+)".*$', '$1') -replace '^(\S+\.exe).*$', '$1'
  if ($p -notmatch '^[A-Za-z]:\\(Windows|Program Files|Program Files \(x86\))\\' -and $p -notmatch '^\\SystemRoot\\|^system32\\') { [pscustomobject]@{ Name = $_.Name; State = $_.State; Path = $p } } }
if (-not $s) { 'Every service runs from Windows or Program Files.'; exit 0 }
'Services that run from other folders (often harmless drivers or tools, sometimes malware):'
$s | Format-Table -AutoSize -Wrap | Out-String -Width 240
exit 1
"""

SCRIPT_FAILED_LOGONS = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 2000 -ErrorAction SilentlyContinue
if (-not $ev) { 'No failed sign-in in the last 7 days (or the Security log cannot be read).'; exit 0 }
"Failed sign-ins in the last 7 days: $(@($ev).Count)"
$ev | ForEach-Object { $x = [xml]$_.ToXml(); $d = @{}; $x.Event.EventData.Data | ForEach-Object { $d[$_.Name] = $_.'#text' }
  [pscustomobject]@{ Account = $d.TargetUserName; Source = $(if ($d.IpAddress -and $d.IpAddress -ne '-') { $d.IpAddress } else { $d.WorkstationName }) } } |
  Group-Object Account, Source | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { "  $($_.Count)x  $($_.Name)" }
if (@($ev).Count -gt 20) { ''; 'Many failures: someone may be guessing passwords (Remote Desktop or file sharing open to the network?).'; exit 1 }
"""

SCRIPT_USB_HISTORY = r"""
'USB storage devices ever connected to this PC:'
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Enum\USBSTOR' -ErrorAction SilentlyContinue | ForEach-Object {
  Get-ChildItem $_.PSPath | ForEach-Object { $p = Get-ItemProperty $_.PSPath; "  $($p.FriendlyName)" } } | Sort-Object -Unique -OutVariable seen
if (-not $seen) { '  None found. Windows lets only an administrator read this list.' }
"""

SCRIPT_EXEC_POLICY = r"""
'PowerShell execution policy (from the most to the least specific scope):'
Get-ExecutionPolicy -List | Format-Table -AutoSize | Out-String
$m = Get-ExecutionPolicy -Scope LocalMachine
if ($m -eq 'Unrestricted' -or $m -eq 'Bypass') { "LocalMachine is ${m}: downloaded scripts run without any check. RemoteSigned is safer."; exit 1 }
"""

SCRIPT_FIREWALL_PROFILES = r"""
'Windows Firewall profiles:'
Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction, NotifyOnListen | Format-Table -AutoSize | Out-String
$off = Get-NetFirewallProfile | Where-Object { -not $_.Enabled -or $_.DefaultInboundAction -eq 'Allow' }
if ($off) { 'A profile is off or allows every incoming connection: turn the firewall on (Security area).'; exit 1 }
"""

SCRIPT_SMARTSCREEN = r"""
$exp = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' -ErrorAction SilentlyContinue).SmartScreenEnabled
$pol = (Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -ErrorAction SilentlyContinue).EnableSmartScreen
$pua = (Get-MpPreference -ErrorAction SilentlyContinue).PUAProtection
"SmartScreen for apps and files: " + $(if ($pol -eq 0) { 'OFF by policy' } elseif ($exp) { $exp } else { 'Windows default (on)' })
"Block potentially unwanted apps (Defender): " + $(if ($pua -eq $null) { 'unknown' } else { @{0='off';1='on';2='audit'}[[int]$pua] })
if ($pol -eq 0 -or $exp -eq 'Off' -or $pua -eq 0) { exit 1 }
"""

SCRIPT_ACTIVATION = r"""
$p = Get-CimInstance SoftwareLicensingProduct -Filter "PartialProductKey IS NOT NULL AND Name LIKE 'Windows%'" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { 'The Windows license cannot be read.'; exit 1 }
$state = @{0='Unlicensed';1='Activated';2='Grace period (out of box)';3='Grace period (hardware changed)';4='Grace period';5='Notification (not genuine)';6='Extended grace'}[[int]$p.LicenseStatus]
"Edition: $($p.Name)"
"Channel: $($p.ProductKeyChannel)"
"State:   $state"
"Key ends with: $($p.PartialProductKey)"
if ($p.LicenseStatus -ne 1) { ''; 'Windows is not activated: some settings are locked and the PC shows a watermark.'; exit 1 }
"""

SCRIPT_BROWSER_POLICIES = r"""
$keys = 'HKLM:\SOFTWARE\Policies\Google\Chrome', 'HKCU:\SOFTWARE\Policies\Google\Chrome', 'HKLM:\SOFTWARE\Policies\Microsoft\Edge', 'HKCU:\SOFTWARE\Policies\Microsoft\Edge',
        'HKLM:\SOFTWARE\Policies\BraveSoftware\Brave', 'HKLM:\SOFTWARE\Policies\Mozilla\Firefox'
$found = foreach ($k in $keys) { if (Test-Path $k) { $p = Get-ItemProperty $k; $p.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object { [pscustomobject]@{ Key = $k -replace '^HK..:\\SOFTWARE\\Policies\\', ''; Setting = $_.Name; Value = "$($_.Value)" } } } }
if (-not $found) { 'No browser is managed by policies: homepage and search engine are the user''s choice.'; exit 0 }
'Browser settings forced by policies (normal in companies; at home they often come from adware that locks homepage, search or extensions):'
$found | Format-Table -AutoSize -Wrap | Out-String -Width 240
exit 1
"""

# ---------- updates and versions ----------

SCRIPT_WINDOWS_SUPPORT = r"""
$v = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$build = [int]$v.CurrentBuild; $disp = $v.DisplayVersion; $ed = $v.EditionID
$w11 = $build -ge 22000
# End of servicing of Home and Pro editions (Microsoft lifecycle).
$eos = @{ 19045 = '2025-10-14'; 22621 = '2024-10-08'; 22631 = '2025-11-11'; 26100 = '2026-10-13'; 26200 = '2027-10-12' }
"Windows " + $(if ($w11) { '11' } else { '10' }) + " $disp (build $build.$($v.UBR)), edition $ed"
if ($eos.ContainsKey($build)) {
  $end = [datetime]$eos[$build]
  "End of support for Home and Pro: $($end.ToString('yyyy-MM-dd'))" + $(if ($end -lt (Get-Date)) { ' - EXPIRED: no more security updates' } else { " ($([int]($end - (Get-Date)).TotalDays) days left)" })
  if ($end -lt (Get-Date).AddDays(90)) { ''; 'Install the latest feature update (Windows Update > Download and install) or plan an upgrade.'; exit 1 }
} else { 'This build is not in the list: check Windows Update for the latest version.' }
"""

SCRIPT_OFFICE = r"""
$c = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration' -ErrorAction SilentlyContinue
if (-not $c) {
  $msi = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match '^Microsoft Office (Professional|Standard|Home)' } | Select-Object -First 1
  if ($msi) { "$($msi.DisplayName) $($msi.DisplayVersion) (classic installer)"; 'Office 2016 and 2019 left support in October 2025: plan Microsoft 365 or Office 2024.'; exit 1 }
  'Microsoft Office is not installed.'; exit 0
}
"Products: $($c.ProductReleaseIds)"
$old = $c.ProductReleaseIds -match '2016|2019' -and $c.ProductReleaseIds -notmatch 'O365|2021|2024'
if ($old) { 'Office 2016 and 2019 left support in October 2025: no more security updates. Plan Microsoft 365 or Office 2024.' }
"Version:  $($c.VersionToReport)   Architecture: $($c.Platform)"
"Updates enabled: " + $(if ($c.UpdatesEnabled -eq 'False') { 'NO' } else { 'yes' })
if ($c.UpdatesEnabled -eq 'False' -or $old) { exit 1 }
"""

SCRIPT_BROWSER_VERSIONS = r"""
$list = @(
  @('Google Chrome', "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"),
  @('Microsoft Edge', "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"),
  @('Mozilla Firefox', "$env:ProgramFiles\Mozilla Firefox\firefox.exe", "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"),
  @('Brave', "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe", "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"),
  @('Opera', "$env:LOCALAPPDATA\Programs\Opera\opera.exe")
)
foreach ($b in $list) {
  $f = $b[1..($b.Count - 1)] | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($f) { $i = Get-Item $f; "{0,-16} {1}   (file date {2})" -f $b[0], $i.VersionInfo.ProductVersion, $i.LastWriteTime.ToString('yyyy-MM-dd') }
}
''; 'A browser not updated for more than a month misses security fixes: open its About page to update it.'
"""

SCRIPT_BIOS_AGE = r"""
$b = Get-CimInstance Win32_BIOS; $bb = Get-CimInstance Win32_BaseBoard
$age = if ($b.ReleaseDate) { [math]::Round(((Get-Date) - $b.ReleaseDate).TotalDays / 365.25, 1) } else { $null }
"Motherboard: $($bb.Manufacturer) $($bb.Product)"
"BIOS/UEFI:   $($b.Manufacturer) $($b.SMBIOSBIOSVersion), released $(if ($b.ReleaseDate) { $b.ReleaseDate.ToString('yyyy-MM-dd') })" + $(if ($age) { " ($age years ago)" })
if ($age -gt 3) { ''; 'Older than three years: the maker may have fixes for stability, memory compatibility, security and the 2023 Secure Boot certificates.'; exit 1 }
"""

# ---------- system integrity ----------

SCRIPT_EVENT_LOG_SIZES = r"""
'Event logs: size, limit and what happens when they are full:'
Get-WinEvent -ListLog Application, System, Security, Setup, 'Microsoft-Windows-PowerShell/Operational' -ErrorAction SilentlyContinue |
  Select-Object LogName, @{n='Used MB';e={[math]::Round($_.FileSize / 1MB, 1)}}, @{n='Limit MB';e={[math]::Round($_.MaximumSizeInBytes / 1MB)}}, LogMode, RecordCount |
  Format-Table -AutoSize | Out-String -Width 200
$small = Get-WinEvent -ListLog Application, System -ErrorAction SilentlyContinue | Where-Object { $_.MaximumSizeInBytes -lt 20MB }
if ($small) { 'System or Application logs are small: errors older than a few days are lost before anyone reads them.'; exit 1 }
"""

SCRIPT_VERIFIER_STATUS = r"""
# verifier.exe may write UTF-16: dropping the NUL characters leaves plain text to match.
$q = (verifier /querysettings | Out-String) -replace "`0", ''
# The flags line is in English on every language of Windows; 0x00000000 means no check is active.
if ($q -match 'No drivers are currently verified' -or $q -match 'Flags:\s*0x0{8}\b') { 'Driver Verifier is off (normal).'; exit 0 }
$q
''; 'Driver Verifier is ON: it slows the PC and causes blue screens on purpose. Turn it off unless someone is debugging a driver.'
exit 1
"""

SCRIPT_BOOT_DEBUG = r"""
$b = bcdedit /enum '{current}' | Out-String
$flags = @()
if ($b -match 'testsigning\s+Yes') { $flags += 'test signing (unsigned drivers allowed)' }
if ($b -match 'nointegritychecks\s+Yes') { $flags += 'driver integrity checks off' }
if ($b -match '\bdebug\s+Yes') { $flags += 'kernel debugging on' }
if ($b -match 'bootlog\s+Yes') { $flags += 'boot logging on' }
if ($b -match 'safeboot') { $flags += 'safe mode at every start' }
if (-not $b.Trim()) { 'The start options cannot be read (administrator rights needed).'; exit 0 }
if (-not $flags) { 'Windows starts in the normal, secure mode.'; exit 0 }
'Unusual start options: ' + ($flags -join '; ')
'They weaken security or slow the start; tools, cheats and old drivers leave them behind. Remove them with bcdedit if nobody needs them.'
exit 1
"""

# ---------- storage ----------

SCRIPT_ONEDRIVE = r"""
$acc = Get-ChildItem 'HKCU:\Software\Microsoft\OneDrive\Accounts' -ErrorAction SilentlyContinue | Where-Object { (Get-ItemProperty $_.PSPath).UserFolder }
if (-not $acc) { 'OneDrive is not signed in on this account.'; exit 0 }
foreach ($a in $acc) {
  $p = Get-ItemProperty $a.PSPath
  "Account: $($p.UserEmail)   Folder: $($p.UserFolder)"
  $size = (Get-ChildItem $p.UserFolder -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { -not ($_.Attributes -band 0x400000) } | Measure-Object Length -Sum).Sum
  "  Files kept on this PC: $([math]::Round($size / 1GB, 2)) GB (cloud-only files are not counted)"
}
$kfm = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
''; 'Folders backed up to OneDrive:'
"  Desktop:   " + $(if ($kfm.Desktop -match 'OneDrive') { 'yes' } else { 'no' })
"  Documents: " + $(if ($kfm.Personal -match 'OneDrive') { 'yes' } else { 'no' })
"  Pictures:  " + $(if ($kfm.'My Pictures' -match 'OneDrive') { 'yes' } else { 'no' })
"""

SCRIPT_DUPLICATES = r"""
$roots = 'Downloads', 'Desktop', 'Documents', 'Pictures', 'Videos' | ForEach-Object { Join-Path $env:USERPROFILE $_ } | Where-Object { Test-Path $_ }
$files = Get-ChildItem $roots -Recurse -File -ErrorAction SilentlyContinue | Where-Object Length -gt 1MB
$groups = $files | Group-Object Length | Where-Object Count -gt 1
$md5 = [Security.Cryptography.MD5]::Create()
$clock = [Diagnostics.Stopwatch]::StartNew()
$partial = $false
# A quick fingerprint (first and last 256 KB) first, the full hash only for files whose fingerprints match.
function Sample($f) {
  try { $s = [IO.File]::OpenRead($f.FullName) } catch { return $null }
  try {
    $n = [math]::Min(262144, $s.Length); $buf = New-Object byte[] ($n * 2)
    [void]$s.Read($buf, 0, $n); [void]$s.Seek(-$n, 'End'); [void]$s.Read($buf, $n, $n)
    [BitConverter]::ToString($md5.ComputeHash($buf))
  } finally { $s.Dispose() }
}
$dups = foreach ($g in $groups) {
  if ($clock.Elapsed.TotalSeconds -gt 60) { $partial = $true; break }
  $g.Group | ForEach-Object { [pscustomobject]@{ File = $_; Hash = (Sample $_) } } | Where-Object Hash | Group-Object Hash | Where-Object Count -gt 1 |
    ForEach-Object { $_.Group | ForEach-Object { [pscustomobject]@{ File = $_.File; Hash = (Get-FileHash $_.File.FullName -Algorithm MD5 -ErrorAction SilentlyContinue).Hash } } } |
    Where-Object Hash | Group-Object Hash | Where-Object Count -gt 1
}
if ($partial) { 'The search stopped after 60 seconds: the list below is partial.' }
if (-not $dups) { 'No duplicate files larger than 1 MB in your personal folders.'; exit 0 }
$waste = ($dups | ForEach-Object { $_.Group[0].File.Length * ($_.Count - 1) } | Measure-Object -Sum).Sum
"Duplicate files: $(@($dups).Count) groups, $([math]::Round($waste / 1MB)) MB that could be freed. Nothing was deleted."
$dups | Sort-Object { $_.Group[0].File.Length * $_.Count } -Descending | Select-Object -First 25 | ForEach-Object {
  ''; '  {0:N1} MB x {1}' -f ($_.Group[0].File.Length / 1MB), $_.Count
  $_.Group | ForEach-Object { '    ' + $_.File.FullName } }
"""

SCRIPT_USER_FOLDERS = r"""
'Size of your personal folders:'
# robocopy /L only lists: it walks a folder many times faster than Get-ChildItem and copies nothing.
'Desktop', 'Documents', 'Downloads', 'Pictures', 'Videos', 'Music', 'AppData\Local', 'AppData\Roaming' | ForEach-Object {
  $p = Join-Path $env:USERPROFILE $_
  if (Test-Path $p) {
    $line = robocopy $p NULL /L /S /NJH /BYTES /NFL /NDL /NC /XJ /R:0 /W:0 | Select-String '^\s+Bytes\s*:' | Select-Object -First 1
    $s = if ($line -and "$line" -match ':\s+(\d+)') { [double]$Matches[1] } else { 0 }
    [pscustomobject]@{ Folder = $_; GB = [math]::Round($s / 1GB, 2) } }
} | Sort-Object GB -Descending | Format-Table -AutoSize | Out-String
"""

# ---------- performance ----------

SCRIPT_CPU_THROTTLING = r"""
$c = Get-CimInstance Win32_Processor | Select-Object -First 1
$perf = (Get-Counter '\Processor Information(_Total)\% Processor Performance' -SampleInterval 1 -MaxSamples 3 -ErrorAction SilentlyContinue).CounterSamples | Measure-Object CookedValue -Average
$util = (Get-Counter '\Processor Information(_Total)\% Processor Utility' -SampleInterval 1 -MaxSamples 3 -ErrorAction SilentlyContinue).CounterSamples | Measure-Object CookedValue -Average
"Processor: $($c.Name.Trim())"
"Base clock: $($c.MaxClockSpeed) MHz"
if ($perf) { "Running at: {0:N0}% of the base clock (~{1:N0} MHz)" -f $perf.Average, ($c.MaxClockSpeed * $perf.Average / 100) }
if ($util) { "Load: {0:N0}%" -f $util.Average }
"Power plan: $(powercfg /getactivescheme)"
if ($perf -and $perf.Average -lt 60) { ''; 'The processor runs well below its base clock: power saving plan, battery saver, overheating or a BIOS limit.'; exit 1 }
"""

SCRIPT_GPU_PROCESSES = r"""
$s = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples | Where-Object CookedValue -gt 0.5
if (-not $s) { 'No program is using the graphics card right now.'; exit 0 }
'Programs using the graphics card right now:'
$s | ForEach-Object { if ($_.InstanceName -match 'pid_(\d+).*engtype_(\w+)') { [pscustomobject]@{ PID = [int]$Matches[1]; Engine = $Matches[2]; Use = $_.CookedValue } } } |
  Group-Object PID | ForEach-Object { $p = Get-Process -Id $_.Name -ErrorAction SilentlyContinue
    [pscustomobject]@{ Program = $(if ($p) { $p.ProcessName } else { "PID $($_.Name)" }); 'GPU %' = [math]::Round(($_.Group | Measure-Object Use -Sum).Sum, 1); Engines = (($_.Group.Engine | Select-Object -Unique) -join ', ') } } |
  Sort-Object 'GPU %' -Descending | Select-Object -First 15 | Format-Table -AutoSize | Out-String
"""
