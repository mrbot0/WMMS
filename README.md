# Windows Maintenance Manager

Local Windows maintenance suite for IT technicians. The technician starts it on the PC being serviced
and works from an enterprise web console that runs **offline** on `127.0.0.1`: it assesses nine areas of
the system, proposes improvements, applies them in one click or on a schedule, keeps a history and
produces customer-ready reports.

- **114 maintenance actions** in nine areas, each rated *safe*, *moderate* or *high risk*, browsable in the Actions catalog
- **5 playbooks** (Quick tune-up, Full maintenance, Repair Windows, Security hardening, Performance boost)
- **Live monitor** of CPU, memory, disk, network and processes, refreshed every 2 seconds
- **Schedules** registered in Windows Task Scheduler, running even when the console is closed
- **History and reports**: trends, before/after comparison, HTML/PDF reports with your company branding, CSV and JSON export
- **Python standard library only**: nothing to install besides Python, no internet connection needed

---

## Contents

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [The console](#the-console)
- [Areas and actions](#areas-and-actions)
- [Safety model](#safety-model)
- [Schedules and protected installation](#schedules-and-protected-installation)
- [Command line](#command-line)
- [Data and privacy](#data-and-privacy)
- [Local API](#local-api)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10 or 11 | Windows PowerShell 5.1 (included in Windows) |
| Python 3.9 or newer | Standard library only. Install it **for all users** if you want schedules |
| Administrator rights | Needed to run actions and create schedules; without them the console is read-only |
| A modern browser | Edge or Chrome; the console works offline |

## Quick start

1. Copy the folder to the PC (or clone this repository).
2. Double-click **`start_wmm.bat`**.

The launcher:

1. checks that Python 3.9+ is available;
2. installs or updates the protected copy in `C:\Program Files\WindowsMaintenanceManager` (UAC prompt);
3. runs the **health check** (Python, PowerShell, Windows tools, performance counters, data folder, database integrity, port, rights, installation);
4. opens the console in the browser.

If UAC is declined, the console opens read-only from the current folder. On the first start the
dashboard offers **Run the first full scan**: it assesses all nine areas in about one to three minutes
and changes nothing.

To look around without changing anything, use preview mode:

```
python wmm.py --preview
```

## The console

| Section | Pages |
|---|---|
| **Overview** | Dashboard (overall score, quick actions, today on this PC, visit checklist, technician notes, area tiles, live system, key figures, insights) · Recommendations (all improvements with filters, bulk apply and dismiss) |
| **Optimize** | Performance · Cleanup · Storage · Startup & Apps · Services |
| **Health** | System Integrity · Security · Updates & Drivers · Network |
| **Operations** | Actions (whole catalog: details, sort, multi-select) · Activity (runs and scans in progress, step by step, run again) · Playbooks · Schedules · History · Reports |
| **Support** | User guide: getting started, searchable FAQ, risk levels, shortcuts, diagnostics to copy, areas at a glance |
| **Settings** | Start-up (restore point at every start, start with Windows), report branding, theme, animations (fun / subtle / off), density, dashboard sections, export / import / reset of console preferences, health check, installation status |

Every area page shows a **score from 0 to 100**, charts and descriptive data, the **recommended
improvements** with *Apply* and *Schedule* buttons and a *Fix recommended* button that applies them all,
the list of actions with their risk, the score trend and the recent activity.

Before a run that is not safe, or a batch of actions, the console lists every step in run order with its
risk and the estimated total time. While a run is in progress the browser tab shows its percentage, and
the live log can be copied or downloaded.

Productivity features: command palette (**Ctrl+K**: pages, actions, playbooks, preferences), keyboard
shortcuts (**?** for the list, e.g. `G` then `D` for the dashboard, **Shift+S** scan all, **Shift+C**
collapse all cards), light/dark theme, collapsible cards, sortable and searchable tables with CSV
export, notification center, status bar with agent health (click the machine ID to copy it). The
console reopens the last page used and remembers the scroll position of each page.

Animations have three levels in Settings › Appearance: **Fun** (default: pages and cards arrive one after
the other, hover lifts and wiggles, click ripples, bouncing dialogs and toasts, confetti when a run, a full
scan or the visit checklist completes), **Subtle** (short fades only, the default when Windows animation
effects are off) and **Off** (only spinners and progress bars move).

## Areas and actions

| Area | What it assesses | Actions |
|---|---|---|
| **Performance** | Live CPU/memory/disk/network, top processes, power plan, page file, memory modules, visual effects, Fast Startup, Game DVR, battery health | Power plan High performance / Balanced, visual effects, Fast Startup on/off, Game DVR on/off, transparency on/off, mouse acceleration off, free standby memory, restart Explorer |
| **Cleanup** | Recoverable space in temp folders, update cache, shader caches, crash dumps, Recycle Bin | Temporary files and caches, obsolete Windows components (DISM), empty Recycle Bin, delete crash dumps |
| **Storage** | Volumes and disks, largest folders and files of the profile, browser caches, error reports, thumbnails, Windows.old, restore point storage, Storage Sense | Optimize all drives (TRIM/defrag), browser caches, error reports, thumbnail cache, Delivery Optimization cache, legacy Internet Explorer cache, delete the oldest restore point, Storage Sense; **disk management**: disk health report, SMART failure prediction, volume and partition reports, dirty bit check, C: speed test, restore point storage report, largest folders on C:, rescan disks, TRIM every SSD, defragment hard disks only, bring offline disks online, limit restore point storage to 8%, reserved storage on/off, reduce the hibernation file, system-managed page file, stop last-access updates, Windows Disk Cleanup, delete Windows.old |
| **Startup & Apps** | Startup programs (registry and startup folders), installed applications, third-party scheduled tasks | **Optimize startup** (turns off non-essential programs), per-entry on/off switch |
| **Services** | Start types and states of all services, non-essential services, restore backup | Disable non-essential services, Xbox services, print services, Windows Search on manual, restart Windows Update / Bluetooth services, restore from backup |
| **System Integrity** | Disk health (SMART), stability events, event log errors (7 days), firmware age, Defender and firewall, last repair checks | DISM RestoreHealth, SFC, SFC verify only, CHKDSK online (system or all drives), disk repair at reboot, TRIM, verify and repair WMI, reset Windows Update components |
| **Security** | Defender, firewall, UAC, SmartScreen, Secure Boot, TPM, BitLocker, RDP, SMBv1, insecure SMB guest logons, LSA protection, LLMNR, telemetry level, advertising ID, recent items, local administrators, Guest, restore points | Quick, full and offline scan, update signatures, turn on firewall, disable SMBv1, block SMB guest logons, LSA protection, disable LLMNR, reduce telemetry, turn off advertising ID, clear recent items, create restore point |
| **Updates & Drivers** | Pending Windows updates by severity, update history, devices with errors, third-party driver age, Microsoft 365 / Office Click-to-Run | Check for updates, install updates, scan for new devices and drivers, update Office, update Microsoft Store apps |
| **Network** | Adapters, latency/jitter/packet loss to router, Cloudflare and Google, DNS time, connections | Flush DNS, purge NetBIOS cache, optimize TCP, renew IP, DNS Cloudflare / Google / automatic, reset hosts file (with backup), full network reset |

The overall score is a weighted average of the scanned areas (Security and System Integrity weigh most).
A scan that could not read its data is marked **incomplete** and capped at 50, so a failed collection
never looks healthy.

## Safety model

- **Risk levels.** *Safe* actions (no data loss, no persistent configuration change) can run unattended.
  *Moderate* and *high risk* actions always ask for confirmation, also when scheduled.
- **Restore point first.** Before any action that is not safe, a System Restore point is created; if that
  fails, nothing runs.
- **Restore point at every start.** When the console starts as administrator it creates a restore point
  as an automatic action (Settings › Start-up, on by default), lifting Windows' one-per-day limit for that
  call only.
- **Protected services.** Defender, Windows Update, firewall, networking, audio, GPU and virtualization
  services are never modified. Changed services are backed up and can be restored.
- **Reversible by design.** Startup entries are turned off with the same switch as Task Manager;
  Windows Update reset renames folders instead of deleting them.
- **One job at a time.** A lock shared with scheduled runs prevents two operations from changing the
  system at the same time.
- **Power button.** In a console running as administrator (never in preview or read-only), the power
  button in the top bar stops every Windows Maintenance Manager process on this PC: other consoles,
  scheduled runs in progress and the commands they started, then the console itself. Interrupted runs
  are marked as such at the next start; schedules stay registered.
- **Local only.** The server listens on `127.0.0.1`, checks the `Host` and `Origin` headers, serves only
  known static files, and accepts changes only with the session token that travels in the link the
  launcher opens (never in the served page).

## Schedules and protected installation

Every action can be scheduled once, daily or weekly. Schedules are registered in **Windows Task
Scheduler** (folder `\WindowsMaintenanceManager\`) and run as SYSTEM, so they work with the console
closed and nobody signed in.

Because those tasks run as SYSTEM, the code they load must not be writable by standard users. The suite
refuses to create schedules unless:

- the program runs from the protected copy in `C:\Program Files\WindowsMaintenanceManager`
  (`start_wmm.bat` installs it automatically, or run `python wmm.py --install`), and
- Python is installed **for all users** (python.org installer › *Customize installation* ›
  *Install Python for all users*).

The Schedules page and the health check show which of the two is missing. Schedules created from another
folder show *Program moved* and can be fixed with **Resync**.

**Start with Windows** (Settings › Start-up) registers the task `\WindowsMaintenanceManager\WMM-Autostart`:
at sign-in it starts the console for that user with the highest rights, without a UAC prompt and without
opening the browser (the link is in the console window). For the same reason as the schedules it is
available only from the protected installation.

## Command line

```
python wmm.py                     start the console (asks for administrator rights)
python wmm.py --preview           read-only console; actions are simulated
python wmm.py --port 9000         use another local port (default 8765)
python wmm.py --no-browser        do not open the browser
python wmm.py --install           install or update C:\Program Files\WindowsMaintenanceManager
python wmm.py --auto-install      install/update, then start the installed copy (used by start_wmm.bat)
python wmm.py --run-schedule ID   run a scheduled action and exit (used by Task Scheduler)
python wmm.py --sandbox-test      run every fix for real in Windows Sandbox, check it and test its undo
                                  (--only ID,ID for some tools, --quick for the short ones; needs Windows Sandbox)
```

The original command-line tool `ottimizza_pc.py` (Italian) is still included and works on its own;
the suite reuses its logic.

## Data and privacy

Everything stays on the PC, in the `dati` folder next to the program:

| File | Content |
|---|---|
| `dati/wmm.db` | SQLite history: scans, runs, schedules, settings |
| `dati/servizi-backup.json` | Original start type of every service changed by the suite |
| `dati/registro.txt` | Plain-text log of every change |

Nothing is sent over the network, except the latency test (ping to the router, 1.1.1.1 and 8.8.8.8, one DNS
lookup) and Windows Update when you check or install updates. The `dati` folder is excluded from this
repository.

## Local API

The console uses a JSON API that a future central console can call on each agent. Every payload carries
the `machine_id`. Requests that change something need the `X-WMM-Token` header.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/agent/info` | Agent identity, version, mode |
| GET | `/api/v1/health` | Health check (`?refresh=1` to run it again) |
| GET | `/api/v1/dashboard` | Scores, highlights, trends, recent activity |
| GET / POST | `/api/v1/areas/{area}` · `/areas/{area}/scan` | Area view · new scan |
| POST | `/api/v1/scan` | Scan all areas in parallel |
| GET | `/api/v1/recommendations` | All improvements |
| GET | `/api/v1/actions` · `/playbooks` | Catalog |
| POST | `/api/v1/runs` · `/runs/safe` | Run actions (`confirmed` required for non-safe ones) |
| GET | `/api/v1/runs/{id}` · `/runs/current` · `/activity` | Progress |
| GET | `/api/v1/live?since=` | Live samples |
| POST | `/api/v1/startup/{id}/toggle` | Turn a startup entry on or off |
| GET / POST / PATCH / DELETE | `/api/v1/schedules[/{id}]` | Schedules (`/{id}/resync`) |
| GET | `/api/v1/history` · `/export/{area\|all}.{csv\|json}` | History and export |
| GET / PUT | `/api/v1/settings` | Report branding |

## Architecture

```
start_wmm.bat           launcher: Python check, auto-install, start
wmm.py                  entry point (console, install, scheduled runs)
ottimizza_pc.py         original maintenance engine, reused by the suite
wmm/
  installer.py          protected copy in Program Files
  agent/
    collectors.py       system, cleanup, integrity and services data
    inventory.py        performance, storage, network, startup, security, updates data
    advisor.py          scores and recommendations
    actions.py          action catalog and playbooks
    tools.py            implementations of the extended actions
    jobs.py             one-at-a-time execution, task registry
    scheduler.py        Task Scheduler XML, protection checks
    live.py             performance counters (PDH) sampler
    health.py           health check and dependency verification
    store.py            SQLite history
    core.py             execution context, machine id
  server/api.py         HTTP server and JSON API
  web/                  console: HTML, CSS, vanilla JS, SVG charts
tests/                  unittest suite
docs/superpowers/       design document and implementation plan
```

## Development

```
python -m unittest discover      run the test suite (213 tests)
python wmm.py --preview          try the console without changing the PC
```

The tests use temporary folders and mocked PowerShell, Task Scheduler and registry calls; they do not
change the system. JavaScript has no build step: edit the files in `wmm/web` and reload the page.

## Troubleshooting

| Symptom | Fix |
|---|---|
| *Python was not found* | Install Python 3.9+ from python.org with *Add python.exe to PATH* |
| *Port 8765 is already in use* | Another console is open; close it or start with `--port 9000` |
| *This window is not connected* / access denied | Click **Request access** and answer **Yes** in the confirmation that appears on the desktop of the PC (or open the link printed in the Windows Maintenance Manager window) |
| *Read-only* / administrator rights needed | Click **Restart as administrator** in the banner and approve UAC: the console reopens with full rights |
| Schedules refused | Run from Program Files and install Python for all users (see the health check in Settings) |
| *Scan incomplete* | Some data needs administrator rights or a PowerShell module was unavailable; scan again as administrator |
| Very large `%TEMP%` | Sizes are measured for 20 seconds and shown as a minimum |
