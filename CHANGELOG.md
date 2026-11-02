# Changelog

All notable changes to Windows Maintenance Manager. The console shows the same notes under **What's new**
(sidebar version, status bar or command palette); they come from `wmm/changelog.py`.

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
