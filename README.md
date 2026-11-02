# Windows Maintenance Manager

Local Windows maintenance suite for IT technicians, with an enterprise web console that runs offline on the PC being serviced.

- **Areas:** Performance (live monitor), Cleanup, Storage, Startup & Apps, Services, System Integrity, Security, Updates & Drivers, Network.
- **Operations:** recommendations with one-click fixes, playbooks, activity with live progress, schedules in Windows Task Scheduler, history and exportable reports (HTML, PDF, CSV, JSON).
- **Safety:** actions that are not safe ask for confirmation and create a restore point first; protected services are never changed; the console listens on 127.0.0.1 only and changes need the session token.

## Requirements

- Windows 10 or 11
- Python 3.9 or newer (standard library only). For schedules, install Python **for all users**.

## Start

Double-click `start_wmm.bat`. It checks Python, installs or updates the protected copy in
`C:\Program Files\WindowsMaintenanceManager` (UAC prompt), runs the health check and opens the console.

Other options:

```
python wmm.py --preview        read-only console, nothing is changed
python wmm.py --install        install to Program Files only
python wmm.py --port 9000      use another local port
```

History, reports and settings are stored in the `dati` folder next to the program.

## Tests

```
python -m unittest discover
```

`ottimizza_pc.py` is the original command-line tool the suite builds on; it still works on its own.
