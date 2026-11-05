"""Release notes shown in the console ("What's new") and served by /api/v1/changelog."""

CHANGELOG = [
    {
        "version": "2.11.0",
        "date": "2026-11-05",
        "title": "Several clients on the central server, server backup and move, versioned databases",
        "highlights": [
            "Clients on the central server: for a provider that looks after several companies, every PC belongs to a client and a technician "
            "can be limited to the clients they look after.",
            "Backup and move of the central server: one file encrypted with a password; restored on another PC, the PCs follow it to the new "
            "address without enrolling again.",
            "Versioned databases: before an upgrade changes a database, a copy is kept in dati\\db-backups; if a step fails nothing changes.",
            "The MSI is built (and signed when the certificate is set) by GitHub with every release; MSI installations update with the MSI.",
        ],
        "changes": [
            "Quality: every API route is called by every kind of role in the tests, the console is checked in a browser (every page, the Italian "
            "text and the sign-in, role and approval flows), lint and type checks run on GitHub and main only accepts changes that pass.",
            "Documentation: an administrator manual and a user guide in Italian, and the OpenAPI description of the API (/api/v1/openapi.json).",
            "Italian: more than 100 phrases translated, among them the Company centre, the first scan and the security notes of programs.",
            "Fixed: a job could look finished before the agent was free again.",
        ],
    },
    {
        "version": "2.10.0",
        "date": "2026-11-05",
        "title": "Company centre: central server, company sign-in, approvals and compliance",
        "highlights": [
            "Central server: every PC of the company contacts one server over HTTPS (also from other offices), sends its summary and inventory "
            "and runs the jobs queued for it, within what that PC allows.",
            "Groups, assets and inventory: groups of PCs, asset tag, owner, location, warranty and licenses, hardware and software of every PC, CSV export.",
            "Software from a company catalog with winget, Windows Update rings, compliance baselines with a percentage and the fixes.",
            "Company sign-in with Microsoft Entra ID (OpenID Connect) or Windows and Active Directory accounts, approval by a second person, "
            "API tokens and a PowerShell module.",
        ],
        "changes": [
            "Security: HTTPS on the local network with a certificate made on this PC, encrypted data files, ransomware decoy files and "
            "controlled folder access, a tamper-evident audit log forwarded to syslog or the Windows log.",
            "Reliability: a background agent that runs as SYSTEM from boot, automatic undo of a fix that made things worse, tests on GitHub at every change, "
            "an MSI package for Group Policy or Intune.",
            "Operations: incidents to take charge of with escalation, tickets in Jira, ServiceNow or GLPI, and a monthly executive report as PDF.",
        ],
    },
    {
        "version": "2.9.0",
        "date": "2026-11-05",
        "title": "Accounts, roles and permissions, and much richer settings",
        "highlights": [
            "Accounts: turn them on in Settings › Accounts and security by creating the first administrator. From then on everyone signs in "
            "with a user name and password (and a 6-digit code with two-step verification), and every request is checked against their role.",
            "Users and roles, a page of its own: users with access hours, expiry, temporary passwords, lockout, sessions and bulk actions; "
            "roles that decide which pages are seen, which tools may run in every area and up to which risk, and what may be managed.",
            "Audit log of every sign-in, refusal and change, with filters and CSV export.",
            "Six new sections in Settings: My account, Accounts and security, E-mail/Telegram/webhook, App and connections, Runs and safety, Data and backup.",
        ],
        "changes": [
            "Alerts: SMTP presets, Telegram bot check and chat detection, a webhook for Teams, Slack or Discord, a test per channel, routing per "
            "alert, repeat interval, quiet hours, Italian alerts, a subject prefix, alerts to the users of chosen roles, and the history of what was sent.",
            "Connections: a proxy for the internet, offline mode or a switch per service, and the networks allowed to reach the phone console and the PC sharing.",
            "Runs: a maintenance window for scheduled fixes, a lock on high-risk tools, a reason or ticket number before changes, and confirmation with the PC name.",
            "Data: retention per kind of data, database check and compaction, configuration backup and restore, reset per group and a diagnostic file for support.",
        ],
    },
    {
        "version": "2.8.0",
        "date": "2026-11-05",
        "title": "Blue screens explained, a way back to a good day and the console on your phone",
        "highlights": [
            "Blue screens explained: the stop code of every crash read from its dump, what it means in plain words, what to do, and the drivers "
            "installed in the week before the first crash.",
            "Back to the last good configuration: choose a day when the PC worked well, see every startup value, service, task, hosts line, proxy "
            "setting and antivirus exclusion that changed since, and put back the ones you tick. One click undoes the return.",
            "The console on your phone: pair it once with a code shown on the PC, then read the state of the PC and run reports and safe fixes "
            "from the same network. The code never travels: every request is signed.",
            "An optional assistant: describe the problem in your words and Claude reads this PC with read-only reports, then proposes the fixes in "
            "order as buttons. It never runs a fix by itself.",
        ],
        "changes": [
            "Who slows the startup: boot times over 90 days and the programs, drivers and services Windows measured as slowing them; startup "
            "programs can be removed from startup right there and put back.",
            "Signs of a coming failure: hardware errors, disk retries and resets, file system damage, sudden power losses and blue screens counted "
            "week by week, with the disk and battery forecasts, and an alert when a sign grows.",
            "Suspicious programs: signature and location of every program running or starting with Windows, with optional VirusTotal lookups of "
            "their fingerprints (never the files).",
            "The same reports or safe fixes on several PCs at once, with one table of results and checks.",
            "A periodic report by e-mail or Telegram, in Italian or English: scores, fixes and their checks, failures, alerts, outages and forecasts.",
            "The requests between PCs are now tested against a second PC running in its own process.",
        ],
    },
    {
        "version": "2.7.0",
        "date": "2026-11-05",
        "title": "Guided diagnosis, your own tools and a console fully in Italian",
        "highlights": [
            "Guided diagnosis: next to each problem found by the symptom search, the console reads this PC and tells which fixes are really needed "
            "(for example: network marked Public, discovery service stopped) and which are already fine. Nothing is changed until you choose.",
            "Checks and undo on many more fixes: 82 fixes with a check of their own, the space freed by 30 cleanups, and the precise undo now also "
            "covers power settings, the active power plan and the start type of services.",
            "Your own tools in the Toolbox: a PowerShell script with area, risk, a check read before and after, and an undo script.",
            "The whole console in Italian, not only the Toolbox: pages, help, settings, recommendations, playbooks, routines and script templates.",
        ],
        "changes": [
            "Connection log: router, internet and DNS timed every few minutes, with the outages and their cause; an alert when the connection comes back.",
            "Suspicious changes: startup programs, tasks, services, extensions, proxy, hosts, antivirus exclusions and administrators compared "
            "with the previous check, with an alert.",
            "Network devices against the CISA catalog of known exploited vulnerabilities, to know which firmware to update first.",
            "Disk and battery trend: one reading a day and an estimate of when a disk wears out or the battery drops below 60%.",
            "Remote runs on the PCs of the network: only reports or safe fixes, only where the PC's user allowed them, with signed requests.",
            "Customer report with evidence: the before/after reading of every checked fix and what can still be undone.",
        ],
    },
    {
        "version": "2.6.0",
        "date": "2026-11-04",
        "title": "Toolbox in Italian, search by symptom and fixes that check themselves",
        "highlights": [
            "The Toolbox speaks Italian: the names, descriptions and warnings of all 355 tools, and the search finds them in both languages.",
            "Search by symptom: type \"non vedo gli altri PC\", \"Internet lento\" or \"Start non si apre\" and the Toolbox proposes the reports to read "
            "first and the fixes to try after, in order (43 common problems).",
            "Every fix with a check reads the state before and after it runs and says \"Fixed\", \"Already fine\" or \"Not fixed\" (60 fixes, "
            "from the internet connection to the camera, Defender and Windows Update).",
            "Precise undo for registry fixes: the values a fix is about to change are saved first, and Undo puts back only those. "
            "The restore point stays as the safety net for the whole PC.",
        ],
        "changes": [
            "Network watch: a schedulable scan that sends an e-mail or Telegram alert when a device never seen before joins the network.",
            "Router exposure: the ports the router opened to the internet through UPnP and the device behind each one, with the risky ones explained.",
            "Bluetooth trackers: an unknown device (AirTag, Tile, SmartTag or unnamed) seen in 3 or more scans over an hour is flagged and can raise an alert; "
            "devices you know can be marked as known.",
            "Wi-Fi history: signal, channel and crowding of your network over time, by hour of the day, with every channel or access point change.",
            "Real tests in Windows Sandbox: python wmm.py --sandbox-test runs every fix for real in a throw-away Windows, checks it and tests its undo.",
            "Signed setup and winget package: the release builds a setup (signed when a code-signing certificate is configured) and the winget manifests.",
        ],
    },
    {
        "version": "2.5.0",
        "date": "2026-11-04",
        "title": "30 new fixes in the Toolbox",
        "highlights": [
            "30 new fixes (351 tools in total) for everyday things that stop working: the \"No internet\" warning while the internet works, "
            "Start menu and search, typing in Start, camera, Windows Hello, notifications, Windows Security, Office, Windows Installer, restore points.",
            "Network sharing in two clicks: network discovery and file sharing on Private networks, and a home network marked Public by mistake.",
            "Cleanups that free gigabytes: Windows upgrade leftovers, unpacked NVIDIA and AMD installers, old driver versions.",
        ],
        "changes": [
            "Updates: repair stuck background downloads (BITS), remove update blocks left by tweaking tools, updates for other Microsoft products.",
            "Explorer and display: reset folder views, open big folders faster, full right-click menu on Windows 11 (and back), "
            "no web results in Start search, End task from the taskbar, a fix for screen flicker (MPO) and its undo.",
            "Security: show file extensions, turn off Remote Assistance; reset local Group Policy left by tweaking tools.",
            "Every new fix asks first; the ones that change policies refuse on company (domain) PCs and keep a backup; "
            "old drivers are removed only when no device uses them.",
        ],
    },
    {
        "version": "2.4.0",
        "date": "2026-11-04",
        "title": "Choose the interface each scanner uses",
        "highlights": [
            "Network devices, Wi-Fi and Bluetooth each have an Interface menu next to the scan button; the active adapter is chosen by default.",
            "Network devices can scan any connected adapter, also ones without a gateway (VirtualBox, Hyper-V, a second network card).",
            "Wi-Fi scans with the chosen adapter only, and tells you whether that adapter is connected and to which network.",
        ],
        "changes": [
            "The active network adapter is the one with a gateway and the lowest metric, the route Windows itself uses.",
            "Bluetooth lists the adapters, but Windows always searches with its active one, and the tab says so.",
            "An adapter that disappeared since the page loaded gives a clear message instead of a failed scan.",
            "New and missing devices are compared per network: scanning another adapter no longer marks the devices of your home network as gone.",
            "New route GET /network/interfaces; the scan routes accept {\"interface\": name}.",
        ],
    },
    {
        "version": "2.3.0",
        "date": "2026-11-04",
        "title": "Wi-Fi and Bluetooth scanners in the Network scanner",
        "highlights": [
            "Network scanner in three tabs: Network devices, Wi-Fi and Bluetooth.",
            "Wi-Fi: every network and access point around, with security (open, WEP, TKIP, WPA2, WPA3), signal in % and dBm, band, channel, "
            "connected stations, the channels in use and the least crowded channel for your router.",
            "Bluetooth: paired and nearby devices (Classic and Low Energy), with kind, signal, a rough distance and the ones that are new.",
        ],
        "changes": [
            "Wi-Fi asks Windows for a fresh scan first (WlanScan), so the list is not the cached one; netsh is read in English and Italian.",
            "Advice for your network on each band: weak signal, outdated security, a crowded or overlapping channel; open networks nearby are listed.",
            "When Windows blocks the Wi-Fi list until Location is on, the tab says so and links to the setting.",
            "Bluetooth uses the Windows device enumeration (both kinds at the same time, about 30 seconds); readings are filtered by type.",
        ],
    },
    {
        "version": "2.2.0",
        "date": "2026-11-04",
        "title": "Network scanner, alerts by email and Telegram, program updates, the PCs of the network and browser tests",
        "highlights": [
            "Network scanner (System): every device on your network with name, maker, MAC, open ports, web page and what it is; new devices are flagged.",
            "Alerts by email and Telegram when a scheduled run fails, drive C: is almost full or unsafe programs appear, even with the console closed.",
            "Program updates: the console checks the GitHub releases once a day and installs a new version after checking its SHA-256.",
            "PCs (Operations): the health of other PCs of the network side by side, read-only, through a summary they share with a key.",
            "Every page is now checked in a real browser by the tests, which found and fixed a security score that failed without the administrators list.",
        ],
        "changes": [
            "Network scanner: only private networks of adapters with a gateway, at most 1022 addresses; ping through the Windows ICMP API, the ARP table, "
            "names, 26 common ports and the title of web pages. Telnet, FTP, VNC and Remote Desktop open on a device are pointed out.",
            "Alerts: secrets encrypted with Windows DPAPI, STARTTLS or SSL for email, the same alert at most once a day, a test button.",
            "Updates: .github/workflows/release.yml builds the zip and SHA256SUMS.txt when a v* tag is pushed (tools/build_release.py); "
            "the package is refused if its checksum, its paths or its version do not match.",
            "PCs: sharing is off until you create a key; the key is kept only as a hash, summaries are filtered by type and size, "
            "only local network addresses are contacted, and the firewall rule is limited to the local subnet.",
            "Code: Applications, System Restore and the new features live in wmm/server/features.py; the styles of the newer pages in pages.css.",
        ],
    },
    {
        "version": "2.1.0",
        "date": "2026-11-03",
        "title": "Restore point and undo, complete uninstall, updatable rules, before/after report, Italian interface",
        "highlights": [
            "A restore point before uninstalling a program, removing a Store app or deleting a registry key; History › Undo opens System Restore on it.",
            "Uninstall waits for the program's uninstaller, then offers its leftovers: folders to the Recycle Bin, registry keys with a backup.",
            "The rules of the Applications page (end of support, minimum safe versions, adware) are a data file that can be updated from the project.",
            "Before / After report for the customer: scores at the start of the visit and now, everything done, what is still recommended.",
            "The console speaks Italian: Settings › Appearance › Language (automatic, English, Italiano); the report follows the same language.",
        ],
        "changes": [
            "A restore point made in the last hour is reused; when Windows makes none, nothing changes until you choose to go on without it.",
            "Settings › Start-up: turn the restore point before manual changes off or on.",
            "Leftovers are only folders and keys that belong to the removed program: never a publisher folder, never something another installed program uses.",
            "The rules file is checked before use (dates, versions, patterns) and used only when newer than the one shipped with the program.",
            "The Italian layer translates menus, pages, buttons, tables, dates and the report; paths, commands and program names stay as they are.",
        ],
    },
    {
        "version": "2.0.0",
        "date": "2026-11-03",
        "title": "Applications page, 40 new tools, a sturdier agent and 20 new console functions",
        "highlights": [
            "New Applications page: every installed program with a safety verdict (end of support, versions with known holes, adware), "
            "when it was last used, uninstall, Store apps, app updates with winget and browser cache cleanup.",
            "40 new toolbox tools (321 in total): DNS benchmark, Wi-Fi channels, suspicious scheduled tasks, unquoted service paths, "
            "failed sign-ins, Windows and Office end of support, duplicate files, TCP/IP reset, search index rebuild and more.",
            "Sturdier agent: closed tabs no longer leave errors in the log, more requests answered in parallel, idle connections freed, "
            "History in write-ahead mode, reads that hang end with a clear message.",
            "20 new console functions: notes for this PC, On this page, table search highlight, Markdown and JSON export, "
            "programs in the command palette, links to a page tab and more.",
        ],
        "changes": [
            "Applications: suggestions (unsafe programs, two antivirus, remote access tools, programs unused for months, several versions "
            "of the same product, leftover entries, preinstalled Store extras, large browser caches).",
            "Applications: last use from Windows (Start menu, taskbar, running programs; Prefetch when run as administrator), "
            "programs installed in the last 30 days, size of an install folder on request.",
            "Applications: uninstall starts the program's own uninstaller read again from Windows, never a command sent by the page; "
            "leftover entries are removed with a registry backup; every change is recorded in History and simulated in preview.",
            "Applications: clear the cache of Chrome, Edge, Brave, Vivaldi, Opera and Firefox (logins, passwords and history stay), "
            "and the list of old setup files left in Downloads.",
            "Toolbox: 11 fixes (TCP/IP and adapters, IPv4 preference, power plans, performance counters, search index, winget sources, "
            "component store reset, Driver Verifier off, RemoteSigned policy) and 29 reports.",
            "Toolbox: duplicate files compares a quick fingerprint before the full hash and stops after a minute; folder sizes use robocopy.",
            "Tables: the search text is highlighted, a double-click copies a cell, MD copies a Markdown table, JSON downloads the rows, "
            "the sort is remembered.",
            "Navigation: links open a page tab (#/apps?tab=security), Shift and the arrows change tab, Shift J jumps to a card, "
            "Shift F searches the table, the menu shows the number of unsafe programs.",
            "Console: notes for this PC (Shift N), auto-refresh of a page, agent response time in the status bar, a log of page errors "
            "to copy for support, scroll progress, refresh after five minutes away, offline notice.",
        ],
    },
    {
        "version": "1.9.0",
        "date": "2026-11-03",
        "title": "47 new tools, tabs on long pages, a better script editor and a hidden start with Windows",
        "highlights": [
            "47 new toolbox tools (281 in total): energy and sleep analysis, speed test, drivers, runtimes, Secure Boot 2023, Defender exclusions, unexpected shutdowns and more.",
            "Long pages are split into tabs: the area pages, the dashboard, Hardware and Schedules show the overview first and the details after.",
            "Script editor: Edit button, snippets, line and column, warnings for dangerous commands, Ctrl S and Save and run.",
            "Start with Windows opens the console in the browser and keeps the Python window hidden.",
            "21 more settings and 40 more functions across the pages.",
        ],
        "changes": [
            "Appearance: menu width, shadows, typeface, centered page, hide the status bar, no hover tooltips.",
            "Behaviour: split long pages into tabs, actions in the search, scan at start, live figures refresh, only warnings and errors as messages.",
            "Notifications: blinking tab title, the result read aloud, scheduled runs since the last visit.",
            "Maintenance: Activity panel at the start of a run, ask before long runs, temperature alert and sensor refresh.",
            "Data: hide the device name, show hidden improvements again, reset page filters; Reset this section in every section.",
            "Dashboard: weakest area, copy the visit checklist, time stamp in the notes. Recommendations: group by area, snooze for 7 days.",
            "Area pages: score change since the previous scan, summary as .txt. History: only failures, most run actions, reset filters.",
            "Event Viewer: saved filters, copy sources. Task Manager: copy the top 10. Registry: recent keys, copy a value as a .reg line.",
            "Hardware: snapshot and compare, old drivers flagged and filtered, copy the IDs of devices with problems.",
            "Schedules: duplicate a schedule, CSV export. Scripts: search and sort, Add and edit for ready-made scripts.",
            "My playbooks: save a selection from Actions, copy any playbook and delete your own. Toolbox: list view, copy the selection.",
            "Activity: copy the session summary. Reports: notes saved as a draft, common phrases. Support: Windows settings shortcuts, problem report.",
            "Category pages: weakest page and copy summary. Focus mode (F), [ and ] for the previous and next page, recent runs and Windows settings in the search.",
            "The console can run hidden (--hidden): output goes to dati\\wmm-console.log and the programs it starts open no window.",
            "Toolbox and Actions are one page: areas and filters on the side (kind, risk, sort, favorites, never run), stars on every tool, "
            "Select visible, Save as playbook and a selection bar. Old links to Actions open the Toolbox.",
            "Schedules: New schedule offers a searchable list of actions and of routines; the Task Scheduler column shows what Windows itself "
            "reports (last result in words); Test starts the Windows task now, as SYSTEM.",
            "Schedules: one-time schedules start an hour from now and cannot be set in the past; the default time of the others is midday.",
        ],
    },
    {
        "version": "1.8.0",
        "date": "2026-11-03",
        "title": "20 new settings and 40 new functions across the pages",
        "highlights": [
            "Settings has two new sections, Notifications and Maintenance, a search box and 20 new options.",
            "Pin any page to the dashboard with the star in its header.",
            "Privacy mode (Shift P) hides serial numbers, MAC addresses and IDs for screen sharing.",
            "Copy and export everywhere: status, improvements, area summaries, playbook steps, reports, hardware inventory.",
            "Schedules: run now, pause all, and the next 7 days at a glance.",
        ],
        "changes": [
            "Appearance: square corners, color-blind friendly status colors, reduced transparency, wider text spacing, underlined links.",
            "Formats: 24 or 12-hour time, three date styles, Windows or decimal sizes.",
            "Behaviour: ask before closing the tab during a run, single-key shortcuts can be turned off.",
            "Notifications: sound volume and test, quiet hours, desktop alerts only for problems, progress in the tab title on or off.",
            "Maintenance: default time and startup wait for new schedules, warning before long runs on battery, report outputs opened or not.",
            "Data: privacy mode and clearing recent commands and pages.",
            "Dashboard: pinned pages, Copy status, change of the overall score since the last visit; the auto-refresh label shows the chosen interval.",
            "Recommendations: copy as a Markdown checklist, CSV export, select every one-click fix.",
            "Every area page: Copy summary, a warning when the scan is a week old, a link to all its runs in History.",
            "Cleanup: free space on C: after the cleanup.",
            "History: Today period, Run again on every row, Copy log, area filter from links.",
            "Event Viewer and Task Manager: search online; Task Manager: copy the path.",
            "Registry: copy the key as a PowerShell path or a reg query command.",
            "Hardware: JSON export, temperature history per sensor, an alert when a sensor gets too hot.",
            "Scripts: duplicate and copy the content. Playbooks: copy the steps, estimated end time.",
            "Activity: estimated end time of the run. Toolbox: Favorites and Safe only filters.",
            "Reports: copy as text and an email draft. Support: copy the PC specifications.",
            "Command palette: pin this page, copy a link to it, open any Settings section, privacy mode, clear recent items.",
        ],
    },
    {
        "version": "1.7.0",
        "date": "2026-11-02",
        "title": "Routines in Schedules and the Hardware page",
        "highlights": [
            "Routines: several actions run together at every startup, at every sign-in, or every day, week or month.",
            "12 suggested routines with their frequency ready (Fresh start, Daily protection, Weekly tune-up, Monthly Windows check…); every playbook can run as a routine too.",
            "New Hardware page (System): every component with its hardware IDs and links to the driver catalog, live temperatures and fans.",
            "One click installs and starts LibreHardwareMonitor, so processor, motherboard and fan sensors appear on desktops too.",
        ],
        "changes": [
            "New frequencies for actions, routines and scripts: at startup or sign-in (with an optional wait), and monthly.",
            "Schedules shows routines with their steps, which ones are active, and the next startup or sign-in run.",
            "Playbooks: Schedule button next to Run playbook.",
            "Hardware: system and motherboard, BIOS, processor, memory modules with part numbers, graphics, disks, network, monitors, audio and battery.",
            "All devices: every device Windows sees with class, hardware ID, driver and status; filter by problems, open every ID, copy or export CSV.",
            "Search links for each device: the web, the Microsoft Update Catalog and the PCI/USB ID database.",
            "Copy summary: the PC specifications as text, without serial numbers, for a ticket or a forum.",
            "Shortcut G then Y opens the Hardware page.",
        ],
    },
    {
        "version": "1.6.0",
        "date": "2026-11-02",
        "title": "Settings menu, 10 new preferences, scripts in Schedules and 10 more playbooks",
        "highlights": [
            "Settings has a side menu: General, Appearance, Behaviour, Dashboard, Start-up, Data and security, Guides and shortcuts, This agent.",
            "10 new preferences: start page, dashboard refresh, rows per table, message duration, confirm safe actions, completion sound, "
            "high contrast, live CPU/RAM in the top bar, disconnect after inactivity and history cleanup.",
            "Scripts can be scheduled from the Schedules page too, which now lists every scheduled script.",
            "15 playbooks in five groups: every visit, fix a problem, read-only checks, tune for a use, secure.",
        ],
        "changes": [
            "New playbooks: full health check, security audit, deep cleanup, fix the internet connection, update everything, gaming, privacy, laptop, new PC setup, fix printing.",
            "New schedule asks whether to run a maintenance action or a script.",
            "Figures that are names (a power plan, an event source) wrap on two lines instead of being cut.",
            "History cleanup keeps unfinished runs, scores and schedules and is recorded in History itself.",
        ],
    },
    {
        "version": "1.5.0",
        "date": "2026-11-02",
        "title": "Scripts, the shutdown timer and 40 more tools",
        "highlights": [
            "New Scripts page: upload .bat and .cmd files or write them, run them now or schedule them once, daily or weekly.",
            "Automatic shutdown: shut down or restart in the minutes you choose, with a live countdown you can change or cancel.",
            "13 ready-made scripts: power (shutdown or restart in N minutes, hibernate, sleep, sign out, cancel), maintenance and files.",
            "40 more tools (234 in total): 22 reports and 18 fixes for cleanup, startup, updates, services, network, integrity and security.",
        ],
        "changes": [
            "Startup and security checks: Run keys, Startup folders, sign-in shell, WMI persistence, program hijacks (IFEO), automatic sign-in.",
            "Update tools: Windows Update services, pause status, resume updates, driver updates off or on, Windows version.",
            "Service tools: clear stuck print jobs, restart Network Location and Cryptographic Services, disabled and delayed services.",
            "Network tools: ARP, routing table, DNS cache, saved Wi-Fi networks, AdGuard DNS, Winsock reset.",
            "Integrity tools: restore points, blue screen settings, application crashes, small crash dumps, memory test at the next restart.",
            "Security tools: firewall rules on public networks, shared folders, password policy, WDigest off, PowerShell script logging.",
            "Cleanup: font cache, Windows Installer size, Java, chat and music apps, game launchers and code editors.",
            "Scripts keep the console code page, so accents in paths and messages work in cmd.exe.",
            "Scheduled scripts run as SYSTEM only from the protected installation; every run, schedule and timer is recorded in History.",
        ],
    },
    {
        "version": "1.4.0",
        "date": "2026-11-02",
        "title": "A livelier, more polished console",
        "highlights": [
            "Cards and sections are revealed as you scroll; a soft glow follows the pointer and tiles tilt in 3D.",
            "The sidebar indicator glides to the active page; tabs get an underline that grows into place.",
            "The theme switch spreads the new theme in a circle from the button.",
            "Charts draw themselves: bars grow, lines trace, the score gauge sweeps.",
            "Settings › Appearance › Try them shows the effects; Subtle and Off still keep the console calm.",
        ],
        "changes": [
            "Filter cards keep their distance from the figures below (Event Viewer, Toolbox, Task Manager).",
            "Primary buttons lean toward the pointer; a card pulses when its action starts.",
            "The overall score shows a rising +N when it improved since the last visit.",
            "Toasts show the time left and pause while the pointer is over them.",
            "Back to top shows how far the page is scrolled; the top bar gains a shadow when the page scrolls under it.",
            "A loading line runs under the top bar while a page opens.",
            "Live CPU and memory figures tick when they change.",
            "The dashboard hero has a slow aurora behind the gauge.",
            "Command palette results and dialog buttons arrive one after the other; dialogs blur the page behind.",
            "Links get an underline that slides in; checkboxes pop when ticked; the sidebar animates in at start.",
            "A small secret for the curious (↑ ↑ ↓ ↓ ← → ← → B A).",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-11-02",
        "title": "30 performance tools, category pages and built-in guides",
        "highlights": [
            "30 new performance tools: 10 reports (CPU, memory, GPU, power, temperatures, disk latency, leaks…) and 20 tweaks (194 tools in total).",
            "Every category is a page: Overview, Optimize, Health, System, Operations and Help, each with its child pages, score and safe fixes.",
            "The dashboard shows all the categories with every page and its score.",
            "Guides: a short tip the first time each page opens, the full guide with ? or F1, and a guided tour.",
            "Hints next to the delicate controls: risks, reports and fixes, process priority, registry backups, schedules.",
        ],
        "changes": [
            "Performance tweaks for CPU (core parking, minimum state, turbo boost), power (PCI Express, disks, sleep), GPU scheduling and network throttling.",
            "Game and foreground priority, animations, tips, Widgets, Copilot and search highlights, frozen app timeouts, prefetch, NTFS cache, adapter power saving.",
            "Sidebar categories open their page; the chevron folds their pages away and is remembered.",
            "Breadcrumbs link back to the dashboard and to the category.",
            "Previous, next and All of… links at the bottom of every page.",
            "Category pages: score, open improvements, tools, scan the whole category and apply its safe fixes.",
            "Command palette: categories, Guide for this page, Take the guided tour, Show all page tips again.",
            "Settings › Guides and help: tips on or off, show them again, take the tour.",
            "The first scan screen shows every category and a link to the guide.",
            "Keyboard focus moves to the new page and screen readers announce it.",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-11-02",
        "title": "Event Viewer, Task Manager, Registry editor and one-click protected installation",
        "highlights": [
            "Event Viewer: critical Windows, hardware, application, service and security events in under a second, with live refresh.",
            "Task Manager: every process with CPU, memory, I/O, user, parent, command line and more; end, end tree, priority and start new processes.",
            "Live services: start, stop and restart, with essential services protected.",
            "Registry editor: tree, favorites, search, edit, rename, new and delete, .reg export, with a backup before every change.",
            "Fix automatically: schedules work on any PC, with Python installed for all users when it is missing.",
        ],
        "changes": [
            "Event Viewer presets: critical and errors, hardware, applications, services, security and Defender, everything.",
            "Event filters: time range, log, levels, source, event ID, limit, instant search and column filters, CSV export.",
            "Event timeline coloured by the worst level and the top sources at a glance; full event details with copy.",
            "Task Manager quick filters: apps, background, Windows, service hosts, high CPU, high memory, my processes; user and priority filters.",
            "Task Manager: choose the columns, sort, multi-select and end several processes, pause or change the refresh interval.",
            "Essential processes and services are marked and cannot be ended or stopped; a reused process ID is detected before ending.",
            "Start a process as administrator or with standard user rights (programs, scripts and management consoles).",
            "Registry: protected keys (boot, drivers, accounts, Windows) cannot be deleted; backups listed and restorable.",
            "Every process, service and registry change is recorded in History; preview mode records without changing anything.",
            "The installation warning now explains whether the program or Python is the problem.",
            "New System section in the menu; shortcuts G then L (events), G then M (Task Manager), G then W (registry).",
        ],
    },
    {
        "version": "1.1.0",
        "date": "2026-11-02",
        "title": "Toolbox, report viewer and a faster console",
        "highlights": [
            "50 new tools across every area: 30 read-only reports and 20 fixes (164 tools in total).",
            "New Toolbox page: every tool by area, with Fixes / Reports tabs, search, multi-select and keyboard navigation.",
            "Report viewer: the output of a diagnostic opens in a window you can search, copy, download and print.",
            "Every area page lists its own tools, split into fixes and diagnostics, with Run all diagnostics.",
            "What's new window after every upgrade, also reachable from the sidebar version.",
        ],
        "changes": [
            "Read-only diagnostics are marked as reports and skipped by Apply safe actions.",
            "Apply safe actions appears only where an area has safe fixes.",
            "Actions page: filter by kind (fixes or reports) and a reports counter.",
            "Report and fix badges on every tool card.",
            "Command palette: matches every word in any order, remembers recent commands, opens the Toolbox and What's new.",
            "Shortcut G then K opens the Toolbox.",
            "The browser tab icon shows the progress of a run.",
            "Background polling pauses while the tab is hidden and resumes at once when it is shown.",
            "Live CPU and memory in the top bar turn amber and red under load.",
            "Activity drawer: each finished tool links to its own output.",
            "Toasts can be dismissed with a click and show an icon for their tone.",
            "Error messages from the agent include the HTTP status.",
            "Status bar shows the version and the number of tools.",
            "Refreshed look: translucent top bar, softer cards that lift on hover, accent-tinted page background.",
            "Tool grids, tabs and the report viewer adapt to phone width.",
            "Print stylesheet for the report viewer.",
            "Toolbox remembers the last tab, kind and search.",
            "Toolbox header with tool, fix and report counts and the tools used in the last 7 days.",
            "Toolbox: sort by name, duration or last run, and a Never run filter; / focuses its search.",
            "Accessible tabs with arrow-key navigation and visible focus.",
            "Enter on a focused tool card opens its details.",
            "Report viewer: find in the output with highlighted matches and a match counter.",
            "Report viewer: copy as a Markdown block, ready for a ticket.",
            "Tool details show the kind and open the output of the last run.",
            "Sidebar Toolbox entry shows the number of tools.",
            "Area pages link straight to their area in the Toolbox.",
            "Agent: gzip compression for pages, scripts and data.",
            "Agent: static files revalidated with ETag (304 when unchanged).",
            "Agent: scripts and styles carry the version, so an upgrade never runs a stale cached file.",
            "Agent: Referrer-Policy, Permissions-Policy and Cross-Origin-Opener-Policy headers.",
            "Agent: Server-Timing header on every response.",
            "Agent: /actions accepts area, kind, risk and q filters.",
            "Agent: /agent/info reports tool counts, agent uptime and Python version.",
            "Agent: run results carry the history id of each tool, for direct access to its log.",
            "Agent: error responses carry their HTTP status.",
            "Tests for the toolbox tools, the report kind and the new agent headers.",
            "Version 1.1.0 with release notes in CHANGELOG.md.",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-11-02",
        "title": "First release",
        "highlights": ["Web console, 114 maintenance actions, playbooks, schedules, history and reports."],
        "changes": [],
    },
]
