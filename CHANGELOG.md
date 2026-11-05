# Changelog

All notable changes to Windows Maintenance Manager. The console shows the same notes under **What's new**
(sidebar version, status bar or command palette); they come from `wmm/changelog.py`.

## 2.11.0 — 2026-11-05

**Several clients, server backup and move, and a sturdier project.** Ten improvements:

1. **Reliable tests, protected main**: the race that made a job test fail now and then is fixed (the agent is released before the job
   is marked finished); the main branch accepts only changes whose `tests` check is green.
2. **Browser tests of the critical flows** (`tests/e2e/flows_check.js`): a viewer signs in and sees only what the role allows, a help-desk
   user gets an approval request instead of a run, the administrator approves it and finds users and clients. They run on GitHub too.
3. **Permission matrix** (`tests/test_v211.py`): every route is called without a session, with a role without permissions and with a role
   that has every permission but the ones the route needs; all must be refused before the route runs.
4. **Cleaner code**: `features.py` split in its agent half and its routes (`routes_features.py`); ruff (errors, undefined names, unused
   imports) and mypy with a ratchet (`tools/typecheck.py`: no file may get more type errors) run on GitHub.
5. **The MSI from GitHub**: every release builds `WindowsMaintenanceManager-<version>.msi` with WiX, signs it with the same certificate as
   the setup when the secrets are set, and lists it in `SHA256SUMS.txt`; every change builds it once as a check. A copy installed with the
   MSI updates itself with the MSI (checksum, and signature when present).
6. **Versioned database migrations** (`wmm/agent/migrations.py`): `wmm.db`, `accounts.db` and `central.db` carry their version; before an
   upgrade a copy goes to `dati\db-backups` (last 5 kept), the steps run in one transaction, a database from a newer version is left alone.
   Versions and copies in Settings › Data.
7. **Complete Italian**: a browser check reads every page and tab in Italian and fails on English sentences written by the app (Windows data
   such as service descriptions stays as it is); more than 100 phrases and 25 rules for text with numbers added.
8. **Documentation**: `docs/manuale-amministratore.md` (enterprise installation, MSI, roles, Entra ID step by step, central server, clients,
   move, migrations), `docs/guida-utente.md`, `docs/api.md` and `docs/openapi.json` generated from the routes (`tools/build_docs.py`, also at
   `/api/v1/openapi.json`; the tests fail when it is out of date).
9. **Clients on the central server** (MSP): every PC and enrollment code belongs to a client; a technician limited to some clients sees and
   manages only their PCs, jobs, inventory and exports; what all clients share (server settings, groups, catalog, rings, backup) stays with the
   provider's staff. Company centre › Clients.
10. **Backup and move of the central server** (`wmm/agent/centralmove.py`): one `.wmmcentral` file encrypted with a password (PBKDF2-SHA256
    300 000 rounds, HMAC-SHA256 keystream and seal) with the database and the server certificate; the secrets of the PCs are encrypted again
    for the new PC. A "move to a new address" job sends the PCs to the new server, which they accept because the certificate is the same: no
    PC enrolls again. Company centre › Backup and move.

## 2.10.0 — 2026-11-05

**Company centre: central server, company sign-in, approvals and compliance.** Twenty features:

1. **Central server** (`wmm/agent/central.py`): agents contact the server over HTTPS (pinned self-signed certificate), enroll with a one-time
   code whose secret never travels, sign every request (HMAC-SHA256, time, nonce), send summary, inventory and compliance, and run queued jobs
   (tools, winget, update ring, baseline, inventory) within the level chosen on that PC (reports, safe fixes, everything).
2. **Groups** of PCs: tags, update ring per group, jobs to a group.
3. **Inventory and assets**: hardware (model, serial, BIOS, CPU, RAM, disks, network) and programs of every PC, software search across PCs,
   asset tag, owner, location, purchase, warranty, licenses, CSV export.
4. **Software deployment** (`deploy.py`): a company catalog of winget IDs, install, update or remove on this PC or on groups.
5. **Windows Update rings** (`updatepolicy.py`): deferral of quality and feature updates, target version, pause, active hours through the
   Windows Update for Business policies; update compliance report.
6. **Company sign-in** (`sso.py`): Entra ID or any OpenID Connect provider (authorization code with PKCE; ID token checked for issuer,
   audience, expiry and nonce), Windows and Active Directory accounts (LogonUserW), roles from groups; identities linked by subject, never by name.
7. **HTTPS on the local network** (`tlsutil.py`): RSA 2048 self-signed certificate made in pure Python, used by the phone console, the PC
   sharing and the central server; clients pin its fingerprint.
8. **Approval by a second person** (`governance.py`): moderate and/or high-risk runs become requests; another user with approvals.decide
   approves (the run starts) or rejects; 24-hour expiry.
9. **Tamper-evident audit log**: every entry chained by SHA-256, verification in Settings, forwarding to syslog (RFC 5424, UDP/TCP) and the
   Windows Application log.
10. **Compliance baselines** (`baselines.py`): built-in Security baseline and Business workstation from the 82 read-only checks, custom
    baselines, percentage, fix what fails (also from the central server).
11. **Ransomware protection** (`canary.py`): Controlled Folder Access (on, audit, off) with blocked programs, hidden decoy files and a
    scheduled check that alerts at once.
12. **Encrypted data files** (`securestore.py`): DPAPI machine scope for the JSON data files, transparent reads, conversion both ways.
13. **Background agent** (`service.py`): a Task Scheduler task as SYSTEM from boot with restart on failure (`wmm.py --background`).
14. **Automatic undo**: a fix whose check says "worse" is put back at once, with an alert.
15. **MSI package** (`packaging/wmm.wxs`, `tools/build_msi.ps1`): per-machine, silent install with `CONFIG=` (configuration backup and
    central enrollment code) and `BACKGROUND=1`; `wmm.py --apply-config` and `--install-background`.
16. **Tests on GitHub** (`.github/workflows/tests.yml`): unit and API tests, JavaScript syntax and dictionaries on Windows at every change.
17. **Tickets** (`tickets.py`): Jira, ServiceNow, GLPI or generic JSON, per alert.
18. **Incidents and escalation** (`incidents.py`): every alert becomes an incident to take and close; escalation to channels and roles.
19. **API tokens and PowerShell** (`tools/WMM.psm1`): scoped tokens (never more than the user), Bearer authentication from this PC only.
20. **Executive report** (`pdfreport.py`): a PDF built without extra packages, for this PC or every PC of the central server.

## 2.9.0 — 2026-11-05

**Accounts, roles and permissions, and much richer settings.**

### Users and roles (40 functions, page `#/users`, `wmm/agent/accounts.py`, `wmm/server/accounts_api.py`)

Users: 1 list with search, 2 filter by role, 3 filter by state, 4 create (own or temporary password), 5 edit, 6 delete, 7 copy (role, access
hours, expiry, language, new temporary password), 8 enable / disable, 9 temporary password, 10 force a new password at the next sign-in,
11 unlock after wrong passwords, 12 reset two-step verification, 13 sign out everywhere, 14 access hours per weekday (also across midnight),
15 account expiry, 16 alert contacts (e-mail, Telegram) per user, 17 language per user, 18 notes, 19 details with open sessions,
20 sign-in history, 21 activity from the audit log, 22 bulk enable / disable / role / unlock / expiry / sign out / delete, 23 CSV export,
24 CSV import with temporary passwords. Roles: 25 list with members count, 26 create from a template or another role, 27 edit,
28 permission matrix of pages (what the role sees), 29 tools per area and risk (report, safe, moderate, high), 30 capabilities (schedules,
scripts, registry, processes, services, apps, other PCs, phone, assistant, alerts, settings, backup, users, roles, sessions, audit),
31 copy, 32 compare two roles, 33 delete with reassignment of the members, 34 reset a built-in role, 35 export as JSON, 36 import,
37 two-step verification required per role, 38 members of a role, 39 open sessions of everyone with sign-out, 40 audit log with filters,
paging, CSV export and pruning.

Five built-in roles (Administrator, Technician, Operator, Viewer, Auditor); Administrator always has every permission and at least one
active user keeps the right to manage users and roles. Passwords: scrypt hashes, policy, history; sessions: SHA-256 hashes of random
tokens with idle and absolute timeouts; two-step: TOTP (RFC 6238) with the secret encrypted by DPAPI and codes never accepted twice.
Every API route has a permission (`wmm/server/permissions.py`): an unlisted write needs an administrator. Runs are checked tool by tool.

### Settings (40 functions, `wmm/web/js/settings29.js`, `wmm/agent/appsettings.py`)

My account: 1 profile, 2 change password, 3 two-step set-up and removal, 4 my sessions and sign-out of the others, 5 sign out.
Accounts and security: 6 turn accounts on (first administrator) and off, 7 password length and characters, 8 password history,
9 password expiry, 10 lockout after wrong passwords, 11 idle timeout, 12 maximum session length, 13 one session per user,
14 two-step for administrators, 15 audit retention. E-mail, Telegram, webhook: 16 SMTP presets for 10 providers, 17 Telegram bot check,
18 Telegram chat detection, 19 a test per channel, 20 webhook for Teams, Slack, Discord or JSON, 21 channels per alert, 22 repeat interval,
23 quiet hours, 24 alerts in Italian, 25 subject prefix, 26 alerts to the users of chosen roles, 27 history of sent alerts.
App and connections: 28 organization name, 29 PC name in alerts, 30 console port, 31 language of new users, 32 update check at start,
33 proxy with exceptions, 34 offline mode and a switch per service, 35 allowed networks for the phone console and the PC sharing.
Runs and safety: 36 maintenance window for scheduled fixes, 37 lock on high-risk tools, 38 reason or ticket before changes,
39 confirmation with the PC name. Data and backup: 40 retention per kind of data, database check and compaction, backup and restore of
the configuration (no secrets), reset per group, diagnostic file, and who changed the settings.

## 2.8.0 — 2026-11-05

**Blue screens explained, a way back to a good day and the console on your phone.**

- **Blue screens explained** (`wmm/agent/crashes.py`, `integrity.bsod_explained`, `GET /api/v1/integrity/crashes`, Integrity page): the stop
  code and parameters read from the header of each dump in `C:\Windows\Minidump` (`PAGEDU64`/`PAGEDUMP`), plus the bugchecks of the System
  log whose dump was deleted; 26 common codes explained in Italian and English with what to do and the tools that help; the drivers
  installed (UserPnp 20001/20003) in the week before the first crash of each kind are listed as suspects.
- **Who slows the startup** (`wmm/agent/boot.py`, `startup.slow_boot`, `GET /api/v1/startup/boot`, Startup page): Diagnostics-Performance
  events 100-103, boot time trend (earlier against recent half), culprits ranked by seconds lost, matched with the startup entries so they
  can be removed from startup and put back (the existing toggle, recorded in History). Needs administrator rights to read the log.
- **Signs of a coming failure** (`wmm/agent/early_warning.py`, `integrity.early_warning`, `GET /api/v1/integrity/early-warning`): WHEA,
  disk 7/11/51/153, storport resets 129, NTFS 55, Kernel-Power 41 and bugchecks of the last 7 days against the 4 weeks before, plus the
  disk and battery forecasts of the daily trend; new alert `early_warning`.
- **Back to the last good configuration** (`wmm/agent/goodconfig.py`, `/api/v1/security/good-config`, Security page): every check of
  Suspicious changes keeps a dated copy (`dati/drift_snapshots/`, 90 days). A plan compares a day with now; each operation has its exact
  opposite (Run values, startup files moved to quarantine, service start types, tasks disabled, hosts lines, proxy values, antivirus
  exclusions). Only the ticked operations run, after a restore point, in one PowerShell process that receives them as base64 JSON;
  the opposites are kept in `dati/goodconfig_last.json` for "Undo the return". What cannot be rebuilt is listed for a manual check,
  with the undoable fixes run since that day.
- **Suspicious programs** (`wmm/agent/suspicious.py`, `security.suspicious_programs`, `/api/v1/security/suspicious`): running processes,
  Run keys, startup folders (shortcut targets), services and non-Microsoft tasks; Authenticode status, SHA-256, and flags for invalid
  signatures, Windows names outside Windows, temporary/download/public folders, double extensions and encoded scripts at startup.
  Optional VirusTotal lookups of the hashes of flagged files (your key, DPAPI-encrypted; at most 4 a check; cached 7 days).
- **Console from the phone** (`wmm/agent/phone.py`, `wmm/web/phone.html`, `wmm/web/js/phone.js`, PCs page): a second port (default
  8767) that answers only local addresses; a one-time 16-character code (80 bits, 10 minutes) is the secret of the phone, never sent:
  every request is signed with HMAC-SHA256 (SHA-256 implemented in the page, since `crypto.subtle` needs HTTPS), with timestamp,
  nonce and replay protection. Summary, open problems, reports and safe fixes only. Phones can be removed; firewall rule for the local
  subnet only.
- **Several PCs at once** (`fleet.start_batch`, `fleet.batch_status`, `/api/v1/fleet/batch`): the same reports or safe fixes on this PC and
  the chosen PCs in parallel, one table of results and checks; each PC still decides what it accepts.
- **Two real PCs in the tests** (`tests/fleet_peer.py`): the other PC runs in its own Python process with its own data folder, key and
  port; the tests read its summary, run and refuse tools, replay a captured request and run a batch over TCP.
- **Periodic report** (`wmm/agent/digest.py`, `integrity.periodic_report`, Settings › Notifications): the period since the last delivered
  report (at most a month), in Italian or English, with a preview; sent with the alert channels.
- **Assistant** (`wmm/agent/assistant.py`, `/api/v1/assistant`, Toolbox): optional; the official `anthropic` package (installed on request)
  and your own API key (DPAPI). Claude Opus 5.5 with six tools: search problems and tools, guided diagnosis, read-only reports, the PC
  summary and fix proposals that come back as buttons. Fixes are never run by the assistant; report output is treated as data.

## 2.7.0 — 2026-11-05

**Guided diagnosis, your own tools and a console fully in Italian.**

- **Guided diagnosis** (`wmm/agent/diagnose.py`, `POST /api/v1/symptoms/<id>/diagnose`): for every fix of a symptom that has a check,
  the check is read now (read-only, in parallel, each script once) and the fix is marked Needed or Already fine; fixes without a check
  stay as "try if the others do not help". The Toolbox shows it with "Guided diagnosis" and "Run the recommended fixes".
- **More checks and a wider undo**: 22 more explicit checks (82 in all); 30 cleanups are judged by the free space on C: before and
  after (Space freed / Nothing to free). The undo journal (`wmm/agent/undo.py`) now also records power settings changed through
  `tools.power_settings` (AC and DC index read with `powercfg /query`, language-independent), the active power plan and the start type
  of the services PowerShell fixes declare (`SERVICE_TOUCHES`); Undo puts them back with `powercfg` and `sc config`.
- **Your own tools** (`wmm/agent/custom_tools.py`, `/api/v1/custom-tools`): a PowerShell script with area, kind, risk, duration, warning,
  an optional check (one line, with the healthy value) and an optional undo script that joins the run's journal. Stored in
  `dati\custom_tools.json`, they join the catalog as `custom.<id>`, also in scheduled runs. Toolbox › Your tools.
- **The whole console in Italian** (`wmm/web/js/i18n_pages.js`): 1,170 phrases of the pages, help, settings, recommendations, playbooks,
  routines, script templates, health check and the 2.7 cards, collected by visiting every page in Italian and from the Python modules
  that produce texts; new rules for labels built from a page or a tool name.
- **Connection log** (`network.connection_watch`, `GET/POST /api/v1/network/connection`): router, internet (1.1.1.1, else 8.8.8.8)
  and DNS timed; outages grouped and classified as router/Wi-Fi, provider or DNS; alert "The internet connection dropped" when it is back.
- **Suspicious changes** (`wmm/agent/drift.py`, `security.drift_watch`, Security page): Run keys, startup folders, services, non-Microsoft
  tasks, hosts, proxy, Defender exclusions, browser extensions and local administrators; an empty read never counts as "removed".
- **Known exploited vulnerabilities** (`wmm/agent/kev.py`, `network.kev_report`, Network › Devices): the CISA KEV feed (cached for a day)
  matched on maker and product words of the scanned devices and of the UPnP router.
- **Disk and battery trend** (`wmm/agent/trends.py`, `storage.health_trend`, Hardware page): SMART wear, temperature, errors and hours,
  battery full-charge against design capacity, one reading a day, least-squares estimate of the end.
- **Remote runs on the fleet** (`wmm/agent/fleet.py`): the sharing PC chooses Off, Reports only, or Reports and safe fixes; requests are
  HMAC-SHA256 signed with the hash of the key (the key never travels), carry a timestamp (two minutes) and a nonce (no replay); moderate
  and high-risk tools are always refused. PCs page › Run… and the results with their checks.
- **Customer report with evidence** (`wmm/web/js/report.js`): a Check column in every run table and an "Evidence: before and after"
  section with the readings of each checked fix and what can still be undone.

## 2.6.0 — 2026-11-04

**Toolbox in Italian, search by symptom and fixes that check themselves.**

- **Toolbox in Italian**: names, descriptions and warnings of all 355 tools (`wmm/web/js/i18n_tools.js`, merged by
  `i18n.js`); the Toolbox search ignores accents and matches the English and the Italian text.
  `tests/test_v26.py` fails when a tool has no translation.
- **Search by symptom** (`wmm/agent/symptoms.py`, `GET /api/v1/symptoms?q=`): 43 common problems in Italian and
  English, each with the reports to read first and the fixes to try after, in order. The Toolbox shows them above the
  results while you type, with "Run the reports" and "Select the fixes".
- **Before/after check** (`wmm/agent/verify.py`): 60 fixes read a state before and after they run (internet and DNS,
  network profile and discovery, camera, Bluetooth, audio, printing, Wi-Fi, Windows Update and BITS, Defender,
  firewall, services, power plan…). The result says Fixed, Already fine, Not fixed or Worse; registry fixes without a
  check of their own say Applied or Already set. Shown in the run panel and in History (new Check column).
- **Precise undo** (`wmm/agent/undo.py`, `POST /api/v1/history/runs/<id>/undo`): the registry write helpers record
  the previous value (and type, or "absent") of every value a fix touches; PowerShell-based fixes declare theirs.
  Undo puts back exactly those values. The restore point stays as the safety net and is still in History.
- **Network watch** (`network.watch`): schedulable scan with an e-mail or Telegram alert (new alert "A new device
  joined the network") when a device never seen before joins.
- **Router exposure** (`wmm/agent/upnp.py`, `network.upnp_report`, Network › Devices): SSDP discovery and
  `GetGenericPortMappingEntry` on the router's WAN service; every forward with the device behind it and a plain
  explanation of the risky ports (RDP, SMB, Telnet, camera streams, NAS pages…). Read-only, local network only.
- **Bluetooth trackers** (`network.bt_watch`, Network › Bluetooth): unpaired trackers or unnamed devices seen in 3 or
  more scans over at least an hour are flagged as possibly following, with an alert; "Mark as known" silences them.
- **Wi-Fi history** (`network.wifi_watch`, Network › Wi-Fi): every Wi-Fi scan stores signal, channel, band and how
  many networks share the channel; the page shows the average signal by hour, the weakest hour and every channel or
  access point change.
- **Windows Sandbox tests** (`wmm/sandbox.py`, `python wmm.py --sandbox-test [--only IDS] [--quick]`): writes a `.wsb`
  that maps the program and Python read-only, runs every fix for real through the normal job runner, checks its
  result and its undo, and writes `dati\sandbox\out\results.json` and `report.txt`. Needs the Windows Sandbox
  feature; nothing runs on this PC.
- **Signed setup and winget** (`packaging/WindowsMaintenanceManager.iss`, `tools/build_installer.ps1`,
  `tools/winget_manifest.py`): the release workflow builds an Inno Setup installer into Program Files, signs it and its
  uninstaller when the `WMM_SIGN_PFX_BASE64` / `WMM_SIGN_PASSWORD` secrets exist, adds it to `SHA256SUMS.txt` and
  writes the winget manifests (`mrbot0.WindowsMaintenanceManager`, depends on Python 3.12).

## 2.5.0 — 2026-11-04

**30 new fixes in the Toolbox** (351 tools in total, `wmm/agent/tools_extra3.py`).

- **Network**: turn on network discovery and file sharing (Private networks only), mark the current network as
  private, fix the "No internet" warning (connectivity test back to the Microsoft defaults; on Windows 11 24H2 and later
  it restarts the Network List Service, which runs the test there).
- **Updates**: repair background downloads (BITS queue), remove update blocks left by tweaking tools (refuses on a
  domain, `.reg` backup in `%ProgramData%\WMM`), updates for other Microsoft products.
- **Startup & Apps**: repair the built-in apps (Start, Settings, Store), restart the Start menu and search, repair
  notifications (the database is kept renamed), quick repair of Office.
- **Services**: restart the camera, Windows Hello, typing in Start and search (ctfmon).
- **Integrity**: reset local Group Policy (refuses on a domain, copy kept), repair Windows Installer, repair restore
  points and backups (VSS, writer states read by number so it works in any language).
- **Security**: repair the Windows Security app, show file extensions, turn off Remote Assistance.
- **Performance**: reset folder views, open big folders faster, full right-click menu on Windows 11 and back, no web
  results in Start search, fix screen flicker (MPO) and back, End task from the taskbar.
- **Cleanup**: Windows upgrade leftovers, unpacked NVIDIA and AMD installers, old driver versions (`pnputil` without
  `/force`, so a driver in use is never removed).
- None of them is "safe": "Apply safe actions" never runs them, each asks first and states what it changes. Preview
  mode simulates them.

## 2.4.0 — 2026-11-04

**Choose the interface each scanner uses.**

- Each tab of the Network scanner has an **Interface** menu next to its scan button, with the active adapter chosen by
  default (`GET /network/interfaces`, read in parallel for the three scanners).
- **Network devices**: every connected adapter with an IPv4 address can be scanned, also those without a gateway
  (VirtualBox, Hyper-V, a second network card). The active one is the adapter with a gateway and the lowest metric.
- **Wi-Fi**: the fresh scan (`WlanScan`) and `netsh wlan show networks interface=<name>` use only the chosen adapter;
  the connected network is the one of that adapter.
- **Bluetooth**: the adapters are listed (active first), but Windows always searches with its active adapter, so the
  menu is informative and the tab says so.
- `POST /network/scan` and `POST /network/(wifi|bluetooth)/scan` accept `{"interface": name}`; an unknown adapter gives
  400 with a clear message.
- New and missing devices are compared per network: a scan on another adapter keeps the history of the others and does
  not list their devices as gone.

## 2.3.0 — 2026-11-04

**Wi-Fi and Bluetooth scanners in the Network scanner.**

- The Network scanner now has three tabs: **Network devices**, **Wi-Fi** and **Bluetooth** (`wmm/agent/radio.py`).
- **Wi-Fi**:
  - a fresh scan through the Windows Wi-Fi API (`WlanScan`), then `netsh wlan show networks mode=bssid`, read in
    English and Italian;
  - every access point with security (open, WEP, TKIP, WPA2, WPA3), signal in % and dBm, band, channel, connected
    stations and maker;
  - the channels in use and the least crowded channel (on 2.4 GHz only 1, 6 and 11);
  - advice for your network on each band (weak signal, outdated security, crowded or overlapping channel) and the open
    networks nearby;
  - when Windows needs Location to list networks, the tab says so and links to the setting.
- **Bluetooth**:
  - paired and nearby devices through the Windows device enumeration, Classic and Low Energy at the same time (about
    30 seconds);
  - kind (controller, phone, headphones, light, tracker…), signal in dBm, a rough distance, devices new since the
    previous scan.
- Both only listen: nothing is joined or paired. Routes: `GET`/`POST /network/wifi(/scan)` and
  `GET`/`POST /network/bluetooth(/scan)`.

## 2.2.0 — 2026-11-04

**Network scanner, alerts by email and Telegram, program updates, the PCs of the network and browser tests.**

- **Network scanner** (`wmm/agent/netscan.py`, System › Network scanner):
  - every device on the private networks of adapters with a gateway (a network larger than /22 is reduced to the /24 of
    this PC);
  - ping through the Windows ICMP API, the ARP table (devices that ignore ping), DNS/NetBIOS names, 26 common TCP ports,
    the title of web pages and the maker from the MAC prefix (random MACs are recognised);
  - a guess of the kind of device (router, PC, printer, NAS, camera, TV, phone, smart home), new devices since the
    previous scan and devices no longer seen;
  - Telnet, FTP, VNC and Remote Desktop open on a device are pointed out. It only reads.
- **Alerts by email and Telegram** (`wmm/agent/notify.py`, Settings › Notifications):
  - a scheduled run that failed, drive C: under 10% or 10 GB, new unsafe programs;
  - bot token and password encrypted with DPAPI (machine scope, so scheduled runs as SYSTEM can read them);
  - STARTTLS or SSL, the same alert at most once a day, a test button.
- **Program updates** (`wmm/agent/updater.py`, Settings › This agent):
  - the latest GitHub release is checked once a day;
  - the zip is installed only if it matches SHA256SUMS.txt, has no path outside its folder and is the announced
    version; data is never touched and the protected copy keeps its permissions;
  - `.github/workflows/release.yml` and `tools/build_release.py` build the release when a `v*` tag is pushed.
- **PCs of the network** (`wmm/agent/fleet.py`, Operations › PCs):
  - a PC can share a read-only summary (scores, improvements, unsafe programs, free space on C:) on a second port,
    with a key kept only as a hash;
  - the console gathers the summaries of the PCs in its list, contacts only local network addresses and filters every
    field by type and size;
  - the firewall rule is limited to the local subnet.
- **Browser tests** (`tests/test_e2e.py`, `tests/e2e/console_check.js`):
  - Playwright opens all 27 pages and checks script errors, error boxes, page tabs, the keyboard shortcuts and the
    Italian interface;
  - skipped where Node.js and Playwright are missing.
  - They found a security score that failed when the administrators list could not be read: fixed in `advisor.py`.
- **Code**: Applications, System Restore and the new features moved from `wmm/server/api.py` to
  `wmm/server/features.py` (`ApiError` in `errors.py`); the styles of the newer pages moved to `css/pages.css`.

## 2.1.0 — 2026-11-03

**Restore point and undo, complete uninstall, updatable rules, before/after report, Italian interface.**

- **Restore point before manual changes** (`wmm/agent/restore.py`): uninstall, Store app removal and deleted registry
  keys make a restore point first (one from the last hour is reused).
  - If Windows makes none, the agent answers 412 and changes nothing; the page asks whether to go on without it.
  - The point number is recorded in History; History › Undo shows the point made before a change and opens System
    Restore (`GET /restore-points`, `POST /restore-points/open`).
  - Settings › Start-up turns it off.
- **Complete uninstall**: the page follows the uninstaller (`GET /apps/{id}/uninstall-status`) and, once the program is
  gone, offers its leftovers (`POST /apps/{id}/leftovers`).
  - Folders go to the Recycle Bin; registry keys are deleted with a .reg backup.
  - Safeguards: only folders inside Program Files, ProgramData and AppData, no names shared by many programs or equal
    to the publisher, nothing another installed program uses.
- **Updatable rules** (`wmm/data/app_rules.json`): end of support, minimum safe versions, adware, optimizers, remote
  access and Store extras.
  - "Update the rules" downloads the file from the project repository, validates it (dates, versions, patterns that
    compile, 512 KB at most) and keeps it in the data folder only when it is newer.
- **Before / After report**: the scores of every area at the chosen moment and now, operations done by area, programs
  removed or updated, errors and the improvements still recommended.
- **Italian interface** (`wmm/web/js/i18n.js`): Settings › Appearance › Language (automatic, English, Italiano).
  - A dictionary of the visible phrases plus rules for counts, relative times and dates.
  - Data (paths, commands, program names, logs) is never touched; customer reports follow the same language.
  - Long tool descriptions and server texts stay in English for now.

## 2.0.0 — 2026-11-03

**Applications page, 40 new tools, a sturdier agent and 20 new console functions.**

- **Applications** (`wmm/agent/apps.py`, `#/apps`, G then Z):
  - Every program from the Uninstall keys and the Store apps, with a safety verdict:
    - unsafe: end of support (Office 2016, 2019 and 2021, .NET 5-7, Python 3.10 and older, Node.js, Flash, Skype…),
      versions with holes used in real attacks (WinRAR < 7.13, 7-Zip < 25.01, VLC < 3.0.21, PuTTY < 0.81), adware;
    - review: remote access tools, "optimizers" and driver updaters, no publisher, support ending within 90 days.
  - Last use from UserAssist (Start menu, taskbar), running programs and, as administrator, Prefetch; "not used" after
    120 days, never for drivers, runtimes and security software.
  - Suggestions, programs installed in the last 30 days, install folder size on request.
  - Uninstall: the program's own uninstaller, read again from the registry (MSI with `/X`); leftover entries removed with
    a registry backup; Store apps with `Remove-AppxPackage`; app updates with winget, one by one or all.
  - Browser caches (Chrome, Edge, Brave, Vivaldi, Opera, Firefox): only cache folders, never cookies, passwords or history.
  - Every change goes through `_logged_change`: administrator, History, simulated in preview.
- **Toolbox** (`wmm/agent/tools_extra2.py`, 321 tools in total): 11 fixes and 29 reports.
  - Fixes: TCP/IP reset, restart adapters, prefer IPv4, IPv6 default, rebuild performance counters, reset power plans,
    rebuild the search index, reset winget sources, component store reset base, Driver Verifier off, RemoteSigned.
  - Reports: DNS benchmark, Wi-Fi networks and channels, NIC errors, DHCP, internet connections, VPN adapters, share sessions,
    suspicious tasks, unquoted service paths, services outside Windows folders, failed sign-ins, USB history, execution
    policy, firewall profiles, SmartScreen, activation, browser policies, Windows and Office support, browser versions,
    BIOS age, event log sizes, Driver Verifier, boot debug, OneDrive, duplicate files, folder sizes, CPU throttling, GPU use.
  - Reports end with `exit 0`, so only "something found" turns them into a warning.
- **Stability**:
  - `AgentServer` ignores tabs closed mid-answer, queues 64 connections, and idle keep-alive connections close after
    two minutes.
  - Error answers to a closed socket no longer raise twice.
  - SQLite in WAL mode.
  - GET requests time out after five minutes and are retried once after a network error; script errors are reported
    once.
- **Console** (`wmm/web/js/upgrade.js`, 20 functions):
  - Tables: search highlight, double-click to copy, Markdown and JSON export, remembered sort.
  - Navigation: `?tab=` links and Copy a link to this tab; Shift + arrows change tab; Shift J (On this page); Shift F
    (search the table); tab counts on Applications.
  - Programs in the command palette and the unsafe counter in the menu.
  - Notes for this PC (Shift N), per-page auto-refresh, agent response time, page error log, scroll progress, refresh
    after five minutes away, offline notice.

## 1.9.0 — 2026-11-03

**47 new tools, tabs on long pages, a better script editor and a hidden start with Windows.**

- **Toolbox** (`wmm/agent/tools_extra.py`, 281 tools in total): 40 read-only reports and 7 fixes.
  - Power and start: energy analysis (`powercfg /energy`), sleep study, what keeps the PC awake and why it wakes, uptime,
    startup impact.
  - Drivers and updates: third-party and old drivers, USB devices, .NET and VC++ runtimes, failed updates, optional
    features, update sharing.
  - Network: speed test (Cloudflare), public IP, proxy, hosts, TCP auto-tuning, network profiles, mapped drives.
  - Security: UAC, SMB, RDP/NLA, Defender exclusions, antivirus products, core isolation, local accounts, expiring
    certificates, Secure Boot 2023 certificates, browser extensions.
  - Errors and disk: unexpected shutdowns, disk and WHEA errors, last CHKDSK, frozen programs, failed services, large
    files, Storage Sense, empty folders, old installers.
  - Fixes: wake timers, update sharing, TCP auto-tuning, ARP cache, Defender cloud protection, RDP NLA, clipboard.
  - Ideas cross-checked with PDQ's list of PowerShell admin checks.
- **Tabs** (`UI.pageTabs`): area pages (Overview, Improvements, Tools, History), dashboard, Hardware and Schedules;
  remembered per page, can be turned off in Settings.
- **Script editor**: visible Edit button, snippets, line and column, warnings for format, rd /s, diskpart, bcdedit and
  similar, Ctrl S, Save and run, Add and edit for ready-made scripts.
- **Start with Windows** runs `pythonw.exe … --hidden`:
  - no console window, and the console opens in the browser;
  - output goes to `dati\wmm-console.log` (rotated at 2 MB);
  - child programs start with `CREATE_NO_WINDOW`;
  - an existing task is updated by turning the option off and on again.
- **Toolbox = Actions**: one page with a side panel (areas, kind, risk, sort, favorites, never run), stars, Select
  visible, Save as playbook and a sticky selection bar; `#/actions` opens the Toolbox.
- **Schedules fixed**:
  - New schedule now offers searchable pickers: "A routine" no longer only scrolls the page.
  - The Task Scheduler column shows the last result reported by Windows (`Get-ScheduledTaskInfo`), and
    `POST /schedules/{id}/test` starts the task as SYSTEM.
  - One-time schedules default to an hour from now and are refused in the past; the default time is midday instead
    of 03:00, when many PCs are off.
- **21 settings and 40 page functions** more (see the release notes in the console).

## 1.8.0 — 2026-11-03

**20 new settings and 40 new functions across the pages.** Everything is in the console; the agent API is unchanged.

- **Settings**: new *Notifications* and *Maintenance* sections and a search box. Appearance: square corners,
  color-blind friendly status colors, reduced transparency, wider text spacing, underlined links. Formats: 24/12-hour
  time, three date styles, Windows (1024) or decimal (1000) sizes. Behaviour: ask before closing the tab during a run,
  single-key shortcuts off. Notifications: volume with a test, quiet hours (they may span midnight), desktop alerts only
  for problems, progress in the tab title. Maintenance: default time and startup wait of new schedules, warning before
  runs of 10+ minutes on battery, open report outputs or not. Data: privacy mode and clear recent commands and pages.
- **Everywhere**: a star in every page header pins it to the dashboard; privacy mode (Shift P) blurs serial numbers,
  MAC addresses, UUIDs and the machine ID; command palette entries for pinning, page links, every Settings section.
- **Dashboard** pinned pages, Copy status, score change since the last visit. **Recommendations** Markdown checklist,
  CSV, select all fixes. **Area pages** Copy summary, week-old scan warning, link to their History. **Cleanup** free
  space after cleanup. **History** Today, Run again, Copy log. **Event Viewer / Task Manager** search online, copy path.
  **Registry** PowerShell path and `reg query`. **Hardware** JSON export, temperature history, high temperature alert.
  **Schedules** Run now, Pause all / Resume all, next 7 days. **Scripts** duplicate, copy content. **Playbooks** copy
  steps, end time. **Activity** end time. **Toolbox** Favorites and Safe only. **Reports** copy as text, email draft.
  **Support** copy PC specifications.

## 1.7.0 — 2026-11-02

**Routines in Schedules and the Hardware page.**

- **Routines**: a group of actions on one schedule. New frequencies for actions, routines and scripts: *at every startup*
  and *at every sign-in* (Task Scheduler boot and logon triggers, with an optional 0–60 minute wait) and *every month*
  (days 1–28). Schedules stores `routine:<id>` or `playbook:<id>` in `action_id`; a `delay` column is added to existing
  databases on start.
- **12 suggested routines** in five groups (at startup, at sign-in, every day, week, month), each with its frequency
  ready, and every playbook can be applied as a routine (also from the Playbooks page). `GET /api/v1/routines`.
- **Hardware page** (System › Hardware, `G` then `Y`): system and motherboard, BIOS, processor, memory modules, graphics,
  disks, network, monitors, audio, battery and every PnP device with hardware IDs, driver version and status; links to
  the web, the Microsoft Update Catalog and the PCI/USB ID database; copyable summary without serial numbers.
  `GET /api/v1/hardware`.
- **Temperatures and fans**, live every 5 s (`GET /api/v1/hardware/sensors`): Windows thermal zones, disk temperatures,
  NVIDIA GPUs (nvidia-smi) and, when LibreHardwareMonitor or OpenHardwareMonitor runs, every CPU, motherboard and fan
  sensor. `POST /api/v1/hardware/monitor-tool` installs LibreHardwareMonitor with winget and starts it (administrator,
  recorded in History).

## 1.6.0 — 2026-11-02

**Settings menu, 10 new preferences, scripts in Schedules and 10 more playbooks.**

- **Settings** now has a side menu with eight sections, one shown at a time and remembered.
- **10 new preferences**: start page, dashboard refresh interval, rows per table, message duration, confirmation for safe
  actions, completion sound, high contrast, live CPU/RAM in the top bar, disconnect after inactivity, history cleanup
  (`POST /api/v1/history/prune`, administrator only, recorded in History, keeps unfinished runs).
- **Schedules** lists the scheduled scripts (run now, change, remove) and *New schedule* offers an action or a script.
- **Playbooks**: 10 new ones (full health check, security audit, deep cleanup, fix the internet connection, update
  everything, gaming, privacy, laptop, new PC setup, fix printing), shown in five groups; read-only ones show *Report*.
- **Layout**: audited every page at 1366 and 1024 px; figures that are names now wrap instead of being cut
  (Event Viewer top source, Performance power plan).

## 1.5.0 — 2026-11-02

**Scripts, the shutdown timer and 40 more tools** (234 tools in total).

- **Scripts page** (Operations): upload `.bat` / `.cmd` files or write them in the editor; run now (output shown when
  they finish) or schedule them once, daily or weekly in Task Scheduler. Scheduled scripts run as SYSTEM, so they need
  the protected installation. Files are kept in the console (OEM) code page so cmd.exe reads accents correctly.
- **Automatic shutdown**: shut down or restart in any number of minutes (presets 5 min – 4 h), live countdown, +15 min /
  +1 h, change the time or the action, cancel. It uses `shutdown /t`, so it happens even if the console is closed.
- **13 ready-made scripts**: shut down / restart in N minutes, shut down now, hibernate, sleep, sign out, cancel the
  planned shutdown, clean temporary files, flush DNS, empty the Recycle Bin, synchronize the clock, back up a folder,
  close a program. Their parameters are validated before they are written into the batch file.
- **40 more tools**: 22 reports and 18 fixes across cleanup, startup, updates, services, network, integrity and security
  (Run keys, Startup folders, Winlogon, WMI persistence and IFEO checks; update services, pause, driver updates; print
  queue, NLA and CryptSvc; ARP, routes, DNS cache, Wi-Fi profiles, AdGuard DNS, Winsock reset; restore points, crash
  settings, app crashes, small dumps, memory test; firewall rules, shares, password policy, automatic sign-in, WDigest,
  PowerShell logging; font, Java, chat/music, game launcher and editor caches).

## 1.4.0 — 2026-11-02

**A livelier, more polished console.** Every effect follows Settings › Appearance › Animations: full at *Fun*, plain
fades at *Subtle*, nothing at *Off* (Windows "reduce animations" picks Subtle by default).

- Scroll reveal for cards, figures, sections and pages; a pointer-following glow on cards; 3D tilt on tiles and figures;
  primary buttons that lean toward the pointer; a pulse on the card whose action starts.
- Sidebar indicator that glides to the active page and items that slide in at start; tab underlines that grow into place.
- Circular theme switch from the button (View Transitions); aurora behind the dashboard gauge; bars that grow and lines
  that draw themselves; a rising +N when the overall score improved since the last visit.
- Toasts with a time bar that pauses on hover; back-to-top with a scroll-progress ring; top bar shadow on scroll; a
  loading line while a page opens; live CPU/RAM figures that tick on change; staggered palette results and dialog buttons.
- Layout: filter cards and toolbars keep their spacing from the figures below (Event Viewer, Toolbox, Task Manager).
- Settings › Appearance › *Try them* to see the effects, and a small secret.

## 1.3.0 — 2026-11-02

**30 performance tools, category pages and built-in guides** (194 tools in total).

- **Performance reports**: processor, memory modules, graphics, power plans, temperatures, disk latency, handle and memory
  leaks, Windows experience scores, page file usage, network adapters and power saving.
- **Performance tweaks**: keep every core awake, CPU at full clock on AC, CPU minimum back to default, aggressive turbo
  boost, PCI Express power saving off, disks never spin down, never sleep on AC, hardware-accelerated GPU scheduling,
  network throttling off, game priority, foreground boost, animations off, tips and suggestions off, Widgets off, Copilot
  off, search highlights off, faster close of frozen apps, prefetching restored, larger NTFS cache, adapters kept awake.
- **Category pages** (`#/cat-…`): Overview, Optimize, Health, System, Operations, Help & settings, each with its child pages,
  category score, open improvements, tools, scan of the whole category and its safe fixes. Sidebar categories open them and
  fold away; breadcrumbs link to them; every page ends with previous / next / All of… links.
- **Dashboard**: an *All categories* section with every page and its score (also on the first-scan screen).
- **Guides**: a short "How this page works" tip the first time each page opens, the full guide with the ? button or F1,
  a guided tour, hints next to delicate controls, and Settings › Guides and help.
- Usability: one-line top bar title, focus and screen-reader announcement on page change, new palette commands.

## 1.2.0 — 2026-11-02

**Event Viewer, Task Manager, Registry editor and one-click protected installation.** New *System* section in the menu.

- **Event Viewer**: critical and error events, hardware (WHEA, Kernel-Power, disk, NTFS, GPU drivers…), applications (crashes,
  hangs, .NET), services, security and Defender. Filters by time, log, level, source and event ID; instant search, column
  filters, CSV, timeline and top sources; live refresh every 10 seconds.
- **Task Manager**: every process with CPU, private memory, disk/network I/O, threads, handles, uptime, user, parent, session,
  priority, company, description, version, hosted services, path and command line. Quick filters, user and priority filters,
  selectable columns, multi-select; end process or process tree, change priority, open the file location, start new processes
  as administrator or as a standard user. Live services tab with start, stop and restart.
- **Registry editor**: key tree, address bar, favorites and bookmarks, edit / rename / delete values of every type, new and
  delete keys, search with a time budget, `.reg` export. A `.reg` backup is made before every change and can be restored;
  keys Windows needs to boot or sign in cannot be deleted.
- Essential processes and services are protected; every change is recorded in History and only simulated in preview mode.
- **Fix automatically** for schedules: the "Not protected" warning was real (the console ran with the per-user Microsoft
  Store Python) but its advice did not fix it. The button now finds or installs a Python for all users (winget, or the
  signed python.org installer), moves the program to Program Files if needed, records the Python in `python.path` so every
  start uses it, registers the schedules again and restarts the console.

## 1.1.0 — 2026-11-02

**Toolbox, report viewer and a faster console.**

### 50 new tools (164 in total)

| Area | New tools |
|---|---|
| Cleanup | GPU shader caches, Microsoft Teams cache, application crash dumps, Office document cache, developer package caches |
| System Integrity | Component store analysis, boot configuration, reliability history, blue screen report, unsigned drivers, recovery environment status |
| Services | Stopped automatic services, restart Wi-Fi / Windows Search / Windows Time, SysMain to manual |
| Performance | Heaviest processes, battery report, USB selective suspend off, faster menus, no startup delay, Game Mode |
| Storage | Temporary folders size, old files in Downloads, Recycle Bin size, page/swap/hibernation files, TRIM status, turn on TRIM |
| Network | Connectivity test, Wi-Fi details, Wi-Fi history report, full IP configuration, listening ports, Quad9 DNS |
| Startup & Apps | Third-party scheduled tasks, boot time history, third-party services, installed applications, stop Edge preloading |
| Security | BitLocker, TPM, Secure Boot, local administrators, Defender status, network protection, controlled folder access (audit) |
| Updates & Drivers | Installed updates, pending restart check, available app updates (winget), devices with problems |

Read-only diagnostics are now marked as **reports**: they are listed apart, open their output when they finish
and are never part of *Apply safe actions*.

### 40+ improvements

The full list is in `wmm/changelog.py` and in the console. Highlights:

- **Toolbox page** with area tabs, Fixes / Reports switch, search, sorting, Never run filter, multi-select and keyboard navigation.
- **Report viewer**: find with highlights, copy, copy as Markdown, download and print.
- Area pages list their tools split into fixes and diagnostics, with *Run all diagnostics*.
- What's new window after an upgrade; smarter command palette with recent commands; `G` then `K` opens the Toolbox.
- Run progress in the browser tab icon; polling pauses in hidden tabs; colored live CPU / RAM.
- Refreshed look: translucent top bar, lifted cards, accent-tinted background, tool cards with kind stripe.
- Agent: gzip, ETag / 304, versioned static URLs, extra security headers, Server-Timing, `/actions` filters,
  `/changelog`, richer `/agent/info`, run results with their history id.

## 1.0.0 — 2026-11-02

First release: web console, 114 maintenance actions, playbooks, schedules, history and reports.
