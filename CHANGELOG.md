# Changelog

All notable changes to Windows Maintenance Manager. The console shows the same notes under **What's new**
(sidebar version, status bar or command palette); they come from `wmm/changelog.py`.

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
