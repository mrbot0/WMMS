"""Forty more toolbox tools (iteration 12): the checks technicians run by hand with powercfg, netsh,
PowerShell and WMI. Reports are read-only and exit with 1 when they find something worth a look,
so the run shows a warning with a clear note; fixes go through ctx.comando and honor preview mode."""
from __future__ import annotations

from ottimizza_pc import Esito

from . import tools


def ps(ctx, script: str) -> Esito:
    """A PowerShell change (fix): skipped in preview mode like every other command."""
    return ctx.comando(tools.powershell_command(script))


# ---------- performance and power ----------

SCRIPT_ENERGY = r"""
$out = Join-Path $env:TEMP 'wmm-energy-report.html'
powercfg /energy /duration 20 /output $out | Out-Null
if (-not (Test-Path $out)) { 'powercfg could not write the energy report (it needs administrator rights).'; exit 1 }
$html = Get-Content $out -Raw
$errors = ([regex]::Matches($html, 'class="error"')).Count; $warnings = ([regex]::Matches($html, 'class="warning"')).Count
"Energy efficiency analysis (20 seconds of tracing)"
"  Errors:   $errors"
"  Warnings: $warnings"
"  Full report: $out"
""
"Typical findings: USB devices that never suspend, a processor that cannot idle, a power plan with no CPU throttling."
if ($errors) { exit 1 }
"""

SCRIPT_SLEEP_STUDY = r"""
$out = Join-Path $env:TEMP 'wmm-sleepstudy.html'
powercfg /sleepstudy /output $out /duration 7 2>&1 | Out-Null
if (Test-Path $out) { "Sleep study of the last 7 days: $out"; "Open it in the browser: it shows how much battery each standby session used and what kept the PC awake." }
else { 'No sleep study: this PC does not use Modern Standby (common on desktops), or the report needs administrator rights.' }
"""

SCRIPT_POWER_REQUESTS = r"""
$r = powercfg /requests
$r
$busy = ($r | Where-Object { $_ -and $_ -notmatch '^(DISPLAY|SYSTEM|AWAYMODE|EXECUTION|PERFBOOST|ACTIVELOCKSCREEN):$' -and $_ -notmatch '^None\.$' }).Count
if ($busy) { ''; 'Something is keeping the PC or the screen awake: the entries above say what.'; exit 1 }
"""

SCRIPT_WAKE = r"""
'Last wake source:'; powercfg /lastwake
''; 'Devices allowed to wake the PC:'; powercfg /devicequery wake_armed
''; 'Wake timers:'; powercfg /waketimers
"""

SCRIPT_UPTIME = r"""
$os = Get-CimInstance Win32_OperatingSystem
$up = (Get-Date) - $os.LastBootUpTime
$fast = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction SilentlyContinue).HiberbootEnabled
"Last start:  $($os.LastBootUpTime)"
"Running for: {0} days {1} h {2} min" -f $up.Days, $up.Hours, $up.Minutes
"Fast startup: " + $(if ($fast -eq 1) { 'on (Shut down does not reset Windows: use Restart to clear it)' } else { 'off' })
if ($up.TotalDays -gt 14) { ''; 'More than two weeks without a restart: pending updates and memory leaks pile up. Restart the PC.'; exit 1 }
"""

SCRIPT_WAKE_TIMERS_OFF = r"""
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0
powercfg /setactive SCHEME_CURRENT
'Wake timers disabled on the current power plan (plugged in and on battery).'
"""

SCRIPT_STARTUP_IMPACT = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Diagnostics-Performance/Operational'; Id=101,102,103,106} -MaxEvents 300 -ErrorAction SilentlyContinue
if (-not $ev) { 'No slow-start events recorded: Windows found no program that delays the start.'; exit 0 }
'Programs, drivers and services that slowed down recent starts (milliseconds of delay):'
$ev | ForEach-Object { $x = [xml]$_.ToXml(); $d = @{}; $x.Event.EventData.Data | ForEach-Object { $d[$_.Name] = $_.'#text' }
  [pscustomobject]@{ Item = $(if ($d.FriendlyName) { $d.FriendlyName } else { $d.Name }); Delay = [int]$d.DegradationTime } } |
  Group-Object Item | ForEach-Object { [pscustomobject]@{ Item = $_.Name; Times = $_.Count; 'Worst delay ms' = ($_.Group | Measure-Object Delay -Maximum).Maximum } } |
  Sort-Object 'Worst delay ms' -Descending | Select-Object -First 15 | Format-Table -AutoSize | Out-String -Width 200
exit 1
"""

# ---------- updates, drivers and runtimes ----------

SCRIPT_DRIVERS = r"""
$d = Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DriverProviderName -and $_.DriverProviderName -notmatch 'Microsoft' -and $_.DeviceName }
"Third-party drivers: $(@($d).Count)"
$d | Sort-Object DriverDate | Select-Object @{n='Device';e={$_.DeviceName}}, @{n='Provider';e={$_.DriverProviderName}}, @{n='Version';e={$_.DriverVersion}},
  @{n='Date';e={ if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } }} | Format-Table -AutoSize | Out-String -Width 220
"""

SCRIPT_OLD_DRIVERS = r"""
$limit = (Get-Date).AddYears(-3)
$d = Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DriverDate -and $_.DriverDate -lt $limit -and $_.DriverProviderName -notmatch 'Microsoft' -and $_.DeviceName }
if (-not $d) { 'No third-party driver older than three years.'; exit 0 }
"Third-party drivers older than three years: $(@($d).Count). Check the manufacturer's site for updates (chipset, network, audio and graphics first)."
$d | Sort-Object DriverDate | Select-Object @{n='Device';e={$_.DeviceName}}, @{n='Provider';e={$_.DriverProviderName}}, @{n='Date';e={$_.DriverDate.ToString('yyyy-MM-dd')}},
  @{n='Hardware ID';e={ ($_.HardWareID -split '&SUBSYS')[0] }} | Format-Table -AutoSize | Out-String -Width 220
exit 1
"""

SCRIPT_USB = r"""
'USB devices connected now:'
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'USB*' -and $_.FriendlyName } |
  Sort-Object Class, FriendlyName | Select-Object Class, FriendlyName, Status, @{n='ID';e={ ($_.InstanceId -split '\\')[1] }} | Format-Table -AutoSize | Out-String -Width 200
"""

SCRIPT_RUNTIMES = r"""
$fw = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction SilentlyContinue).Release
$map = [ordered]@{ 533320='4.8.1'; 528040='4.8'; 461808='4.7.2'; 461308='4.7.1'; 460798='4.7'; 394802='4.6.2' }
$v = ($map.GetEnumerator() | Where-Object { $fw -ge $_.Key } | Select-Object -First 1).Value
".NET Framework: " + $(if ($v) { $v } elseif ($fw) { "4.x (release $fw)" } else { 'not found' })
''; '.NET runtimes:'
if (Get-Command dotnet -ErrorAction SilentlyContinue) { dotnet --list-runtimes } else { '  dotnet is not installed (apps that need it install it themselves).' }
''; 'Visual C++ Redistributables:'
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match 'Visual C\+\+' } | Sort-Object DisplayName | ForEach-Object { "  $($_.DisplayName)  $($_.DisplayVersion)" }
"""

SCRIPT_UPDATE_FAILURES = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'; Id=20; StartTime=(Get-Date).AddDays(-60)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No failed update installation in the last 60 days.'; exit 0 }
"Failed update installations in the last 60 days: $(@($ev).Count)"
$ev | ForEach-Object { $_.Message -replace '\s+', ' ' } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15 |
  ForEach-Object { "  $($_.Count)x  $($_.Name)" }
''; 'Search the 0x8... code online, or run Repair Windows Update in the Updates area.'
exit 1
"""

SCRIPT_OPTIONAL_FEATURES = r"""
$on = Get-WindowsOptionalFeature -Online -ErrorAction SilentlyContinue | Where-Object State -eq 'Enabled'
'Optional Windows features turned on:'
$on | Sort-Object FeatureName | ForEach-Object { "  $($_.FeatureName)" }
$risky = $on | Where-Object { $_.FeatureName -match 'SMB1Protocol|TelnetClient|TFTP|MicrosoftWindowsPowerShellV2' }
if ($risky) { ''; 'Outdated features that are better off: ' + (($risky | ForEach-Object FeatureName) -join ', '); exit 1 }
"""

SCRIPT_DELIVERY_PEERS = r"""
$p = Get-DeliveryOptimizationPerfSnapThisMonth -ErrorAction SilentlyContinue
$mode = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config' -ErrorAction SilentlyContinue).DODownloadMode
"Delivery Optimization download mode: " + $(if ($mode -eq $null) { 'Windows default' } else { @{0='HTTP only (no peers)';1='PCs on this network';2='group';3='PCs on this network and on the internet';99='bypass';100='simple'}[[int]$mode] })
if ($p) { "This month: downloaded $([math]::Round($p.DownloadHttpBytes/1GB,2)) GB from Microsoft, uploaded $([math]::Round($p.UploadInternetBytes/1GB,2)) GB to the internet" }
if ($mode -eq 3) { ''; 'The PC uploads updates to strangers on the internet: limit it to the PCs on this network to save upload bandwidth.'; exit 1 }
"""

SCRIPT_DELIVERY_LAN_ONLY = r"""
$k = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config'
if (-not (Test-Path $k)) { New-Item $k -Force | Out-Null }
Set-ItemProperty $k -Name DODownloadMode -Value 1 -Type DWord
'Delivery Optimization limited to the PCs on this network: no uploads to the internet.'
"""

# ---------- network ----------

SCRIPT_SPEED = r"""
$ProgressPreference = 'SilentlyContinue'
try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-WebRequest -Uri 'https://speed.cloudflare.com/__down?bytes=25000000' -UseBasicParsing -TimeoutSec 60
  $sw.Stop()
  $mbps = [math]::Round(($r.RawContentLength * 8 / 1e6) / $sw.Elapsed.TotalSeconds, 1)
  "Download speed: $mbps Mbit/s (25 MB from Cloudflare in $([math]::Round($sw.Elapsed.TotalSeconds,1)) s)"
  $ping = Test-Connection 1.1.1.1 -Count 4 -ErrorAction SilentlyContinue
  if ($ping) { "Latency to 1.1.1.1: $([math]::Round(($ping | Measure-Object ResponseTime -Average).Average)) ms" }
  if ($mbps -lt 10) { ''; 'Below 10 Mbit/s: check the Wi-Fi signal, other downloads and the line.'; exit 1 }
} catch { "The speed test could not reach Cloudflare: $($_.Exception.Message)"; exit 1 }
"""

SCRIPT_PUBLIC_IP = r"""
$ProgressPreference = 'SilentlyContinue'
try { $ip = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=json' -TimeoutSec 15).ip; "Public IP address: $ip" }
catch { "The public address could not be read: $($_.Exception.Message)"; exit 1 }
$v6 = try { (Invoke-RestMethod -Uri 'https://api64.ipify.org?format=json' -TimeoutSec 10).ip } catch { $null }
if ($v6 -and $v6 -ne $ip) { "Public IPv6 address: $v6" } else { 'No public IPv6 address.' }
"""

SCRIPT_PROXY = r"""
'System proxy (WinHTTP, used by Windows Update and services):'; netsh winhttp show proxy
$p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
''; 'User proxy (browsers and apps):'
"  Enabled: " + $(if ($p.ProxyEnable -eq 1) { "yes, $($p.ProxyServer)" } else { 'no' })
"  Automatic script: " + $(if ($p.AutoConfigURL) { $p.AutoConfigURL } else { 'none' })
if ($p.ProxyEnable -eq 1 -or $p.AutoConfigURL) { ''; 'A proxy is set: if this PC is not in a company network, adware may have set it.'; exit 1 }
"""

SCRIPT_HOSTS = r"""
$lines = Get-Content "$env:SystemRoot\System32\drivers\etc\hosts" -ErrorAction SilentlyContinue | Where-Object { $_.Trim() -and $_ -notmatch '^\s*#' }
if (-not $lines) { 'The hosts file has no active entries (normal).'; exit 0 }
"Active entries in the hosts file: $(@($lines).Count)"
$lines | Select-Object -First 60 | ForEach-Object { "  $_" }
''; 'Entries for update, antivirus or bank sites are a classic sign of malware. Reset hosts in the Network area removes them.'
exit 1
"""

SCRIPT_TCP = r"""
$g = netsh int tcp show global
'TCP global settings:'; $g
''; 'Receive window auto-tuning should be "normal"; "disabled" limits downloads on fast lines.'
$m = $g | Select-String -Pattern 'Auto-Tuning Level\s*:\s*(\w+)'
if ($m -and $m.Matches[0].Groups[1].Value -ne 'normal') { exit 1 }
"""

SCRIPT_AUTOTUNING = r"""
netsh int tcp set global autotuninglevel=normal
'Receive window auto-tuning set to normal.'
"""

SCRIPT_CLEAR_ARP = r"""
netsh interface ip delete arpcache
'ARP cache cleared: the PC asks again for the addresses of the devices on the network.'
"""

SCRIPT_NETWORK_PROFILES = r"""
'Network profiles (Public is safer on unknown networks; Private allows sharing and discovery):'
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory, IPv4Connectivity | Format-Table -AutoSize | Out-String -Width 200
$pub = Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Private' -and $_.Name -match 'Guest|Free|Public|Hotel|Airport|Cafe' }
if ($pub) { 'A public-looking network is set as Private: set it to Public in Settings > Network.'; exit 1 }
"""

# ---------- security ----------

SCRIPT_UAC = r"""
$k = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
"UAC enabled:                 " + $(if ($k.EnableLUA -eq 1) { 'yes' } else { 'NO' })
"Prompt for administrators:   " + @{0='never (elevates silently)';1='credentials on secure desktop';2='consent on secure desktop';5='consent for non-Windows programs (default)'}[[int]$k.ConsentPromptBehaviorAdmin]
"Secure desktop:              " + $(if ($k.PromptOnSecureDesktop -eq 1) { 'yes' } else { 'no' })
if ($k.EnableLUA -ne 1 -or $k.ConsentPromptBehaviorAdmin -eq 0) { ''; 'UAC is off or never asks: any program can change the system silently.'; exit 1 }
"""

SCRIPT_SMB = r"""
$s = Get-SmbServerConfiguration -ErrorAction SilentlyContinue
$c = Get-SmbClientConfiguration -ErrorAction SilentlyContinue
"SMB1 server:          " + $(if ($s.EnableSMB1Protocol) { 'ON (outdated, used by WannaCry)' } else { 'off' })
"SMB signing required: server " + $s.RequireSecuritySignature + ", client " + $c.RequireSecuritySignature
"SMB encryption:       " + $s.EncryptData
"Guest logons allowed: " + $c.EnableInsecureGuestLogons
if ($s.EnableSMB1Protocol -or $c.EnableInsecureGuestLogons) { exit 1 }
"""

SCRIPT_RDP = r"""
$deny = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server').fDenyTSConnections
$tcp = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp'
"Remote Desktop: " + $(if ($deny -eq 0) { 'ON' } else { 'off' })
"Network Level Authentication: " + $(if ($tcp.UserAuthentication -eq 1) { 'required' } else { 'NOT required' })
"Port: $($tcp.PortNumber)"
if ($deny -eq 0 -and $tcp.UserAuthentication -ne 1) { ''; 'Remote Desktop accepts connections without Network Level Authentication: turn NLA on.'; exit 1 }
"""

SCRIPT_DEFENDER_EXCLUSIONS = r"""
$p = Get-MpPreference -ErrorAction SilentlyContinue
if (-not $p) { 'Microsoft Defender is not the active antivirus, or its settings cannot be read.'; exit 0 }
$all = @($p.ExclusionPath) + @($p.ExclusionProcess) + @($p.ExclusionExtension) | Where-Object { $_ }
if (-not $all) { 'Defender has no exclusions.'; exit 0 }
"Defender exclusions ($(@($all).Count)):"
if ($p.ExclusionPath) { '  Folders and files:'; $p.ExclusionPath | ForEach-Object { "    $_" } }
if ($p.ExclusionProcess) { '  Processes:'; $p.ExclusionProcess | ForEach-Object { "    $_" } }
if ($p.ExclusionExtension) { '  Extensions:'; $p.ExclusionExtension | ForEach-Object { "    $_" } }
''; 'Malware often adds itself here. Remove any exclusion you do not recognise in Windows Security.'
exit 1
"""

SCRIPT_AV_PRODUCTS = r"""
$av = Get-CimInstance -Namespace root\SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction SilentlyContinue
if (-not $av) { 'No antivirus is registered with Windows Security Center.'; exit 1 }
'Antivirus products registered with Windows:'
foreach ($a in $av) {
  $hex = '{0:X6}' -f $a.productState
  $on = $hex.Substring(2, 2) -in '10', '11'; $fresh = $hex.Substring(4, 2) -eq '00'
  "  $($a.displayName): " + $(if ($on) { 'active' } else { 'not active' }) + ', signatures ' + $(if ($fresh) { 'up to date' } else { 'OUT OF DATE' })
}
if (@($av).Count -gt 1) { ''; 'More than one antivirus: two real-time scanners slow the PC down and can conflict.' }
"""

SCRIPT_DEVICE_GUARD = r"""
$g = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard -ErrorAction SilentlyContinue
if (-not $g) { 'Virtualization-based security cannot be read on this PC.'; exit 0 }
$names = @{1='Credential Guard'; 2='Memory integrity (HVCI)'; 3='System Guard'}
"Virtualization-based security: " + @{0='off';1='enabled, not running';2='running'}[[int]$g.VirtualizationBasedSecurityStatus]
"Running protections: " + $(if ($g.SecurityServicesRunning) { ($g.SecurityServicesRunning | Where-Object { $names[[int]$_] } | ForEach-Object { $names[[int]$_] }) -join ', ' } else { 'none' })
$hvci = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity' -ErrorAction SilentlyContinue).Enabled
"Memory integrity setting: " + $(if ($hvci -eq 1) { 'on' } else { 'off (Windows Security > Device security > Core isolation)' })
"""

SCRIPT_USERS = r"""
'Local accounts:'
Get-LocalUser | Sort-Object Enabled -Descending | Select-Object Name, Enabled, @{n='Last sign-in';e={ if ($_.LastLogon) { $_.LastLogon.ToString('yyyy-MM-dd') } else { 'never' } }},
  @{n='Password expires';e={ if ($_.PasswordExpires) { $_.PasswordExpires.ToString('yyyy-MM-dd') } else { 'never' } }}, @{n='Password required';e={$_.PasswordRequired}} |
  Format-Table -AutoSize | Out-String -Width 200
$noPw = Get-LocalUser | Where-Object { $_.Enabled -and -not $_.PasswordRequired }
if ($noPw) { 'Enabled accounts that do not need a password: ' + (($noPw | ForEach-Object Name) -join ', '); exit 1 }
"""

SCRIPT_CERTIFICATES = r"""
$soon = (Get-Date).AddDays(30)
$c = Get-ChildItem Cert:\LocalMachine\My, Cert:\CurrentUser\My -ErrorAction SilentlyContinue | Where-Object { $_.NotAfter -lt $soon }
if (-not $c) { 'No personal certificate expires in the next 30 days.'; exit 0 }
'Personal certificates expired or expiring within 30 days (VPN, Wi-Fi, e-mail signature, smart card):'
$c | Sort-Object NotAfter | Select-Object @{n='Expires';e={$_.NotAfter.ToString('yyyy-MM-dd')}}, Subject, Issuer | Format-Table -AutoSize | Out-String -Width 220
exit 1
"""

SCRIPT_DEFENDER_CLOUD = r"""
Set-MpPreference -MAPSReporting Advanced -SubmitSamplesConsent SendSafeSamples -CloudBlockLevel High
'Defender cloud-delivered protection on (advanced), safe samples sent automatically, cloud block level high.'
"""

SCRIPT_RDP_NLA_ON = r"""
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name UserAuthentication -Value 1
'Remote Desktop now requires Network Level Authentication.'
"""

SCRIPT_SMB_GUEST_OFF = r"""
Set-SmbClientConfiguration -EnableInsecureGuestLogons $false -Force
'Guest logons to network shares turned off: shares now need a real account.'
"""

SCRIPT_SECURE_BOOT_2023 = r"""
# The Microsoft Secure Boot certificates of 2011 expire in 2026: firmware needs the "Windows UEFI CA 2023" in its db.
try { $sb = Confirm-SecureBootUEFI -ErrorAction Stop } catch { 'Secure Boot cannot be read (legacy BIOS or no administrator rights).'; exit 0 }
"Secure Boot: " + $(if ($sb) { 'on' } else { 'off' })
try {
  $db = [Text.Encoding]::ASCII.GetString((Get-SecureBootUEFI -Name db -ErrorAction Stop).Bytes)
  $has2023 = $db -match 'Windows UEFI CA 2023'
  "Windows UEFI CA 2023 in the firmware database: " + $(if ($has2023) { 'yes' } else { 'NO' })
  $flag = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot' -ErrorAction SilentlyContinue).AvailableUpdates
  if ($flag) { "Pending Secure Boot updates flag: 0x{0:X}" -f $flag }
  if (-not $has2023) { ''; 'The new certificates are missing: install the latest Windows updates and the BIOS/UEFI update of the PC maker.'; exit 1 }
} catch { 'The Secure Boot database cannot be read on this PC.' }
"""

SCRIPT_MAPPED_DRIVES = r"""
'Network drives mapped for this user:'
$m = Get-ItemProperty 'HKCU:\Network\*' -ErrorAction SilentlyContinue
if (-not $m) { '  none' } else { $m | ForEach-Object { "  $($_.PSChildName):  $($_.RemotePath)" } }
''; 'Current state:'; net use
"""

SCRIPT_BROWSER_EXTENSIONS = r"""
function Show-Chromium($name, $root) {
  $prof = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path (Join-Path $_.FullName 'Extensions') }
  foreach ($p in $prof) {
    $ext = Get-ChildItem (Join-Path $p.FullName 'Extensions') -Directory -ErrorAction SilentlyContinue
    if (-not $ext) { continue }
    "$name ($($p.Name)): $(@($ext).Count) extensions"
    foreach ($e in $ext) {
      $man = Get-ChildItem $e.FullName -Recurse -Filter manifest.json -ErrorAction SilentlyContinue | Select-Object -First 1
      $n = if ($man) { try { (Get-Content $man.FullName -Raw | ConvertFrom-Json).name } catch { '' } } else { '' }
      if ($n -like '__MSG_*') { $n = '(localized name)' }
      "  $($e.Name)  $n"
    }
  }
}
Show-Chromium 'Chrome' "$env:LOCALAPPDATA\Google\Chrome\User Data"
Show-Chromium 'Edge' "$env:LOCALAPPDATA\Microsoft\Edge\User Data"
Show-Chromium 'Brave' "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"
Get-ChildItem "$env:APPDATA\Mozilla\Firefox\Profiles" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $j = Join-Path $_.FullName 'extensions.json'
  if (Test-Path $j) { $a = (Get-Content $j -Raw | ConvertFrom-Json).addons | Where-Object { $_.location -eq 'app-profile' }
    "Firefox ($($_.Name)): $(@($a).Count) extensions"; $a | ForEach-Object { "  $($_.id)  $($_.defaultLocale.name)" } }
}
''; 'Remove any extension you did not install yourself: adware often arrives as a browser extension.'
"""

# ---------- system integrity (event logs) ----------

SCRIPT_UNEXPECTED_SHUTDOWNS = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; Id=41, 6008; StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No unexpected shutdown in the last 30 days.'; exit 0 }
"Unexpected shutdowns in the last 30 days: $(@($ev).Count)"
$ev | Sort-Object TimeCreated -Descending | Select-Object -First 20 | ForEach-Object { "  $($_.TimeCreated.ToString('yyyy-MM-dd HH:mm'))  ID $($_.Id)  $(($_.Message -split [Environment]::NewLine)[0])" }
''; 'Repeated ones point to the power supply, overheating, drivers or a failing component. See the blue screen report too.'
exit 1
"""

SCRIPT_DISK_EVENTS = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='disk','Ntfs','stornvme','storahci','volmgr','Microsoft-Windows-Ntfs'; Level=1,2,3; StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No disk or file-system error in the last 30 days.'; exit 0 }
"Disk and file-system warnings and errors in the last 30 days: $(@($ev).Count)"
$ev | Group-Object ProviderName, Id | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object {
  $e = $_.Group[0]; "  $($_.Count)x  $($e.ProviderName) ID $($e.Id): $(($e.Message -split [Environment]::NewLine)[0])" }
''; 'Bad blocks (disk 7), resets (stornvme 129, storahci 129) and Ntfs 55 mean: back up now and check SMART.'
exit 1
"""

SCRIPT_WHEA = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=(Get-Date).AddDays(-60)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No hardware error (WHEA) in the last 60 days.'; exit 0 }
"Hardware errors reported by the processor or the buses (WHEA) in the last 60 days: $(@($ev).Count)"
$ev | Group-Object Id | ForEach-Object { "  $($_.Count)x  ID $($_.Name): $((($_.Group[0].Message) -split [Environment]::NewLine)[0])" }
''; 'Common causes: an unstable overclock or XMP memory profile, overheating, PCIe power saving, a failing device.'
exit 1
"""

SCRIPT_CHKDSK_RESULT = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Chkdsk','Wininit'} -MaxEvents 10 -ErrorAction SilentlyContinue | Where-Object { $_.Id -in 1001, 26226 }
if (-not $ev) { 'No disk check result recorded on this PC.'; exit 0 }
$e = $ev | Sort-Object TimeCreated -Descending | Select-Object -First 1
"Last disk check: $($e.TimeCreated)"
''; $e.Message
if ($e.Message -match 'found problems|corrupt|bad sectors|errors found') { exit 1 }
"""

SCRIPT_FAILED_SERVICES = r"""
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'; Id=7000, 7001, 7009, 7011, 7023, 7031, 7034; StartTime=$boot.AddMinutes(-1)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No service failed to start or crashed since the last start.'; exit 0 }
"Service problems since the last start ($boot): $(@($ev).Count)"
$ev | ForEach-Object { ($_.Message -split [Environment]::NewLine)[0] } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { "  $($_.Count)x  $($_.Name)" }
exit 1
"""

SCRIPT_APP_HANGS = r"""
$ev = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Hang'; Id=1002; StartTime=(Get-Date).AddDays(-30)} -ErrorAction SilentlyContinue
if (-not $ev) { 'No program stopped responding in the last 30 days.'; exit 0 }
"Programs that stopped responding in the last 30 days: $(@($ev).Count)"
$ev | ForEach-Object { ($_.Properties[0].Value) } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { "  $($_.Count)x  $($_.Name)" }
exit 1
"""

# ---------- storage and cleanup ----------

SCRIPT_LARGE_FILES = r"""
'Files larger than 1 GB in your user folder (videos, disk images, old installers, backups):'
$f = Get-ChildItem -Path $env:USERPROFILE -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 1GB -and $_.FullName -notmatch '\\AppData\\Local\\Packages\\' }
if (-not $f) { '  none'; exit 0 }
$f | Sort-Object Length -Descending | Select-Object -First 30 | ForEach-Object { '  {0,8:N1} GB  {1}  {2}' -f ($_.Length / 1GB), $_.LastWriteTime.ToString('yyyy-MM-dd'), $_.FullName }
''; 'Nothing was deleted: move what you keep to an external drive or delete it yourself.'
"""

SCRIPT_STORAGE_SENSE = r"""
$k = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy' -ErrorAction SilentlyContinue
if (-not $k) { 'Storage Sense has never been configured on this account (it is off).'; exit 1 }
"Storage Sense: " + $(if ($k.'01' -eq 1) { 'on' } else { 'off' })
"Runs: " + @{1='every day';7='every week';30='every month';0='when the disk is low'}[[int]$k.'2048']
"Delete temporary files of apps: " + $(if ($k.'04' -eq 1) { 'yes' } else { 'no' })
"Empty the Recycle Bin after: " + $(if ($k.'08' -eq 1) { "$($k.'256') days" } else { 'never' })
"Delete Downloads after: " + $(if ($k.'32' -eq 1) { "$($k.'512') days" } else { 'never' })
if ($k.'01' -ne 1) { exit 1 }
"""

SCRIPT_CLIPBOARD = r"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Clipboard]::Clear()
Get-Service cbdhsvc_* -ErrorAction SilentlyContinue | Restart-Service -Force -ErrorAction SilentlyContinue
'Clipboard and clipboard history cleared (copied passwords and personal data are gone).'
"""

SCRIPT_EMPTY_FOLDERS = r"""
'Empty folders in Documents, Downloads and Desktop (often left by uninstalled programs):'
$roots = 'Documents', 'Downloads', 'Desktop' | ForEach-Object { Join-Path $env:USERPROFILE $_ } | Where-Object { Test-Path $_ }
$e = foreach ($r in $roots) { Get-ChildItem $r -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { -not (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Select-Object -First 1) } }
if (-not $e) { '  none'; exit 0 }
$e | Select-Object -First 80 | ForEach-Object { "  $($_.FullName)" }
"$(@($e).Count) empty folders. Nothing was deleted."
"""

SCRIPT_OLD_INSTALLERS = r"""
'Installers and archives in Downloads older than 30 days:'
$f = Get-ChildItem (Join-Path $env:USERPROFILE 'Downloads') -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in '.exe', '.msi', '.zip', '.7z', '.rar', '.iso' -and $_.LastWriteTime -lt (Get-Date).AddDays(-30) }
if (-not $f) { '  none'; exit 0 }
$f | Sort-Object Length -Descending | ForEach-Object { '  {0,8:N1} MB  {1}  {2}' -f ($_.Length / 1MB), $_.LastWriteTime.ToString('yyyy-MM-dd'), $_.Name }
"Total: {0:N1} GB in {1} files. Nothing was deleted." -f (($f | Measure-Object Length -Sum).Sum / 1GB), @($f).Count
"""
