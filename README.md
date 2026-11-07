# Windows Maintenance Manager (WMM)

**WMM checks, repairs and keeps Windows PCs in shape, one or hundreds of them, from a web console that runs on the PC itself.**

You start it on the PC to fix and work from a console in your browser, on `127.0.0.1`. The console:

- scans nine areas of the system and gives each one a score from 0 to 100;
- explains what is wrong and proposes the fixes;
- applies them with one click or on a schedule, with a restore point before every change;
- keeps a history of everything and produces reports ready to hand to a customer.

In a company the same PCs are managed from a **central server**, with accounts, roles, approvals, compliance and separate clients.

Everything is plain Python (nothing to install besides Python) and works without internet. Nothing leaves the PC unless you turn it on.

The console speaks English and Italian. The administrator manual and the user guide are in Italian, in [docs/](docs/).

---

## Contents

- [Who it is for](#who-it-is-for)
- [What it does](#what-it-does)
- [How changes are kept safe](#how-changes-are-kept-safe)
- [Installation](#installation)
- [First steps](#first-steps)
- [The console, page by page](#the-console-page-by-page)
- [Automation](#automation)
- [In a company](#in-a-company)
- [Data and privacy](#data-and-privacy)
- [Command line](#command-line)
- [API](#api)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## Who it is for

| Who | What they do with it |
|---|---|
| **IT technician** | Visits a customer, starts WMM, scans everything in a couple of minutes, applies the fixes and hands over a before/after report. |
| **Office or small business** | Leaves WMM installed: schedules maintenance, gets alerts by e-mail or Telegram, keeps the PCs updated and safe. |
| **IT department** | Manages every PC from the central server: inventory, software, Windows Update rings, compliance, approvals, and sign-in with company accounts (Entra ID, Active Directory). |
| **Managed service provider (MSP)** | Looks after several customer companies from one server, with technicians limited to the clients they look after. |
| **Non-expert user** | Uses Simple mode: the dashboard says what to fix first, and every recommendation has a plain-language "Why?". |

## What it does

### Scans and recommendations

- **Nine areas** with a score: Cleanup, System Integrity, Services, Performance, Storage, Network, Startup & Apps, Security, Updates & Drivers.
- **Recommendations** sorted by impact. Each one has a **Why?** that explains:
  - what was found and why it matters;
  - what the fix does and its risk;
  - how long it takes and how to go back.
- **What changed since yesterday** on the dashboard: scores up or down, new and solved problems, failed runs.
- **Goals** (for example "free space on C: at least 20%"), with an alert when the PC drifts outside them.

### 370 tools

There are **209 fixes**, which change something, and **160 reports**, which only read. Each tool is rated *safe*, *moderate* or *high risk*.

| Area | Examples |
|---|---|
| Cleanup | temporary files, Windows Update cache, Teams, Office and browser caches, superseded components, Recycle Bin, crash dumps |
| Integrity | SFC, DISM, CHKDSK, blue screens explained, signs of a coming failure, Windows Update reset |
| Services | unnecessary services, telemetry, Xbox, putting back the original state |
| Performance | power plans, visual effects, page file, heaviest processes, "Why is the PC slow right now?" |
| Storage | SMART health, TRIM, largest folders, folder map, duplicate and forgotten files, disk-full forecast, backups to a disk or NAS (copy, mirror, encrypted dated archives with restore) |
| Network | DNS, proxy, Winsock, Wi-Fi, speed test, step-by-step internet check, devices on the network, ports the router opened |
| Startup & Apps | startup programs, what slows the boot, unsafe or unused applications, recently installed programs, uninstall with leftover cleanup |
| Security | Defender, firewall, BitLocker and the recovery key, TPM and Secure Boot, what browser extensions can do, listening ports explained, suspicious programs, ransomware decoy files |
| Updates | Windows Update, old drivers, winget with exceptions, end of support of this Windows, calendar of the updates |

### System tools

- Task Manager and Event Viewer.
- Registry editor, with an automatic backup before every change.
- Services.
- Hardware, with temperatures and an inventory label with a QR code.
- Network scanner: devices, Wi-Fi, Bluetooth, router, known exploited vulnerabilities.
- A toolbox searchable by symptom.

### Reports

- HTML and PDF reports with your company branding: full, per area, or the before/after of a visit. You choose which sections to include.
- An executive PDF report for the central server.
- CSV and JSON export.
- A diagnostic package (zip) for the technician, without passwords or tokens.

## How changes are kept safe

- **Risk levels.** *Safe* tools can run unattended. *Moderate* and *high-risk* tools ask for confirmation, also when scheduled.
- **Restore point first.** Before any change that is not safe, a Windows restore point is created; if that fails, nothing runs.
- **Precise undo.** History shows what every run changed. Where possible, **Undo** puts the previous values back. With automatic undo, a fix that made things worse is reverted by itself.
- **Protected services.** Defender, Windows Update, firewall, networking, audio, graphics and virtualization services are never touched.
- **One job at a time.** Only one job changes the PC at a time, across consoles and schedules.
- **Company rules** (Settings › Runs and safety):
  - block high-risk tools;
  - require a reason or ticket number;
  - confirm with the PC name;
  - **approval by a second person**;
  - maintenance window.
- **Local only.** The console listens on `127.0.0.1`, checks the `Host` and `Origin` headers, and accepts changes only with the token of the link opened at start. With accounts on, every route checks the permissions of the role; tests call every route with every kind of role.

## Installation

### One PC

| Requirement | Notes |
|---|---|
| Windows 10 or 11 | PowerShell 5.1, included in Windows |
| Python 3.9 or newer | Standard library only. Install it **for all users** if you want schedules |
| Administrator rights | Needed to apply fixes; without them the console is read-only |
| A modern browser | Edge or Chrome |

1. Copy the folder to the PC, or clone this repository.
2. Double-click **`start_wmm.bat`**.

The launcher:
1. checks Python;
2. installs or updates the protected copy in `C:\Program Files\WindowsMaintenanceManager` (UAC prompt);
3. runs the health check;
4. opens the console.

A signed `WindowsMaintenanceManager-Setup-<version>.exe` is also in every release.

To look around without changing anything:

```
python wmm.py --preview
```

### Many PCs

Every GitHub release has an MSI, `WindowsMaintenanceManager-<version>.msi`, for Group Policy and Intune:

```
msiexec /i WindowsMaintenanceManager-2.12.0.msi /qn CONFIG="\\server\share\wmm-config.json" BACKGROUND=1
```

The details (Entra ID, roles, central server) are in the [administrator manual](docs/manuale-amministratore.md).

### Updates

Settings › This agent looks for new versions on GitHub and installs them after checking their checksum:

- copies installed with the MSI update with the MSI, and its signature is checked too;
- other copies update with the zip.

Data is never touched.

## First steps

1. **Dashboard › Scan everything.** In one to three minutes every area has a score, and the scan changes nothing.
2. **Recommendations.** Start from the high-impact ones. Press **Why?** to understand, then **Apply**.
3. **Reports.** Download the report for the customer, or the before/after of the visit.
4. **Schedules.** Make maintenance automatic, for example a cleanup every week or a copy of your files every day.
5. **Settings › Overview.** See at a glance what is missing: alerts, backup, protection.

## The console, page by page

| Section | Pages |
|---|---|
| **Overview** | Dashboard (health, what changed, goals, pinned pages) · Recommendations |
| **Optimize** | Performance · Cleanup · Storage · Startup & Apps · Applications |
| **Health** | Services · System Integrity · Security · Updates & Drivers · Network · Hardware |
| **System** | Event Viewer · Task Manager · Registry · Network scanner · Toolbox |
| **Operations** | Activity · Playbooks · Schedules · PCs · Company centre · Scripts · History · Reports |
| **Help & settings** | Support · Settings · Users and roles |

Conveniences:

- **Universal search** (Ctrl K) across pages, tools, settings and commands.
- **Pinned and recent pages** at the top of the menu.
- **Simple mode**, which hides the pages for experts.
- **Themes**: light and dark, high contrast, color-blind friendly colors, larger text.
- **The whole interface in English or Italian.**
- **Tables** with search, filters, saved views, column choice, row selection with bulk actions, and export to CSV, JSON and Markdown.

**Settings** come in six groups, with a search that finds a single option:

| Group | Sections |
|---|---|
| Personal | My account, Appearance, Behaviour, Dashboard, Guides |
| Alerts | Sounds and desktop alerts, Alert channels (e-mail, Telegram, webhook) |
| Maintenance | Runs and safety, Automation, Schedule defaults, Start-up |
| Security and access | Accounts and passwords, Company sign-in, API tokens, Protection, Privacy |
| Organization and integrations | Organization and reports, Connections and console, Integrations |
| System and data | This agent, Backup of your files, Data and backup |

## Automation

- **Schedules** in Windows Task Scheduler, run as SYSTEM even with the console closed. They can run once, daily, weekly or monthly, at startup, at sign-in, or **when the PC is idle**.
- **Playbooks and routines**: several tools in a row, such as "Quick tune-up" or "Full maintenance".
- **Rules "when this happens, run a tool"**: for example, when the disk is almost full, clean the temporary files. Rules run only safe tools.
- **Goals**, with an alert when they are not met.
- **Nightly program updates** with winget, except the programs you exclude.
- **Copy of your files** to another disk or a NAS: only new and changed files, nothing deleted at the destination.
- **Alerts** by e-mail, Telegram, Teams, Slack or Discord, with quiet hours, routing per alert type, and incidents to take charge of.

## In a company

- **Accounts and roles.**
  - Five built-in roles: Administrator, Technician, Operator, Viewer, Auditor.
  - Custom roles with more than 100 permissions: what each role sees, runs and manages.
  - Two-step verification, password policies, sessions.
  - Temporary roles that end by themselves, and periodic access reviews.
- **Company sign-in** with Microsoft Entra ID (OpenID Connect with PKCE) or Windows and Active Directory accounts. The role comes from the groups.
- **Tamper-evident audit log**, hash-chained and verifiable, forwarded to a SIEM (syslog) or a webhook.
- **Central server**: every PC contacts it over HTTPS with a pinned certificate, also from other offices. From the server you manage:
  - hardware and software inventory, and assets;
  - a software catalog with winget;
  - Windows Update rings;
  - compliance baselines with their fixes;
  - **campaigns** with a deadline and progress;
  - a ranking of the PCs that need attention first;
  - an executive PDF report.
- **Several clients** (MSP): every PC belongs to a client, and a technician can be limited to their own clients.
- **Backup and move of the server**: one password-encrypted file. The PCs follow the server to a new address without enrolling again.
- **Integrations**: tickets in Jira, ServiceNow or GLPI, scoped API tokens, and a PowerShell module (`tools/WMM.psm1`).

## Data and privacy

Everything stays on the PC, in the `dati` folder next to the program:

| File | Content |
|---|---|
| `dati/wmm.db` | History: scans, runs, schedules |
| `dati/accounts.db` | Users, roles, sessions, audit log, tokens, approvals |
| `dati/central.db` | Central server (only on the PC that hosts it) |
| `dati/db-backups/` | Copies of the databases made before every schema upgrade |
| `dati/backups.json`, `dati/backup_history.json` | Backup profiles of Storage › Backup (passwords protected with DPAPI) and the last 500 runs |
| `dati/app_settings.json`, `dati/integrations.json` | Settings |
| `dati/*.json` | Network, Wi-Fi and alert history, snapshots; can be encrypted with DPAPI |

Nothing leaves the PC, except:
- the network tests you start;
- Windows Update and winget, when you use them;
- the alerts and integrations you set up;
- the check for new versions, when it is on.

**Offline mode** turns off everything that uses the internet.

## Command line

```
python wmm.py                       start the console (asks for administrator rights)
python wmm.py --preview             read-only console: changes are simulated
python wmm.py --port 9000           another local port (default 8765, or the one in Settings)
python wmm.py --no-browser          do not open the browser
python wmm.py --install             install or update the protected copy in Program Files
python wmm.py --auto-install        install or update, then start the installed copy (used by start_wmm.bat)
python wmm.py --background          background agent: schedules, alerts and central server without a console
python wmm.py --install-background  install the background agent task (as administrator)
python wmm.py --apply-config FILE   apply a configuration backup (silent installations)
python wmm.py --run-schedule ID     run a schedule and exit (used by Task Scheduler)
python wmm.py --sandbox-test        try every fix in Windows Sandbox, with its check and its undo
```

The original command-line tool `ottimizza_pc.py` (Italian) is still included and works on its own; the suite reuses its logic.

## API

The console uses a local JSON API (`/api/v1/…`). Scripts and integrations call it with an API token. The full description, with the permissions of every route, is in [docs/openapi.json](docs/openapi.json); the console also serves it at `/api/v1/openapi.json`. Examples are in [docs/api.md](docs/api.md).

## Architecture

```
start_wmm.bat            launcher: Python check, installation, start
wmm.py                   entry point (console, installation, schedules, background agent)
ottimizza_pc.py          original maintenance engine, reused by the suite
wmm/
  agent/                 the work on the PC
    actions.py           catalog of the 370 tools, playbooks
    collectors.py, inventory.py   data of the areas; advisor.py scores and recommendations
    tools*.py            the fixes and the reports
    jobs.py              one job at a time, automatic undo
    scheduler.py         Task Scheduler (also "when the PC is idle")
    accounts.py, governance.py, sso.py   accounts, roles, approvals, tokens, company sign-in
    central.py, centralmove.py   central server, clients, campaigns, backup and move
    migrations.py        versioned databases, copied before every upgrade
    plus212.py, qrcode.py         2.12 features (diagnosis, files, rules, goals, QR label…)
    store.py             SQLite history
  server/                HTTP server and API (api.py, accounts_api.py, enterprise_api.py, routes_*.py,
                         permissions.py, openapi.py)
  web/                   console: HTML, CSS, JavaScript without a build step, SVG charts, Italian
packaging/, tools/       MSI (WiX), setup, release, docs, type check
tests/                   unit, API, permission and browser tests (Playwright)
docs/                    manuals, OpenAPI
```

## Development

```
python -m unittest discover -s tests -t .   every test (also in a browser when Playwright is installed)
python -m ruff check .                     lint
python tools/typecheck.py                  type check: no file may get worse
python tools/build_docs.py                 rebuild docs/openapi.json after changing a route
python wmm.py --preview                    try the console without changing the PC
```

On GitHub every change goes through:
- unit and API tests;
- the permission matrix on every route;
- browser tests (every page, the Italian text, the sign-in and approval flows);
- lint and types;
- the MSI build.

`main` accepts only changes whose checks are green.

The tests use temporary folders and mock PowerShell, Task Scheduler and the registry, so they never change the system. The JavaScript has no build step: edit the files in `wmm/web` and reload the page.

## Troubleshooting

| Problem | Fix |
|---|---|
| *Python was not found* | Install Python 3.9 or newer from python.org, with *Add python.exe to PATH* |
| *Port 8765 is already in use* | Another console is open: close it, or start with `--port 9000` |
| *This window is not connected* | Click **Request access** and answer **Yes** on the desktop of the PC, or open the link printed in the WMM window |
| *Read-only* | Click **Restart as administrator** and approve UAC |
| Schedules refused | Run from Program Files and install Python for all users (see the health check in Settings) |
| *Scan incomplete* | Some data needs administrator rights: scan again as administrator |

## Documentation

- [Administrator manual](docs/manuale-amministratore.md) (Italian): company installation, MSI, roles, Entra ID step by step, central server, clients, moving the server, migrations
- [User guide](docs/guida-utente.md) (Italian)
- [API and OpenAPI](docs/api.md) (Italian)
- [What changed in every version](CHANGELOG.md)
