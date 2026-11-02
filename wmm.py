"""Windows Maintenance Manager: local Windows maintenance suite with a web console.

Usage:
  python wmm.py                     start the console (asks for administrator rights)
  python wmm.py --preview           start without administrator rights; nothing is changed
  python wmm.py --port 9000         use another local port (default 8765)
  python wmm.py --no-browser        do not open the browser
  python wmm.py --run-schedule ID   run a scheduled action (used by Task Scheduler)
  python wmm.py --install           install to C:\\Program Files\\WindowsMaintenanceManager
  python wmm.py --auto-install      install or update that copy, then start it (start_wmm.bat)

The console listens on 127.0.0.1 only. History and reports live in the `dati` folder.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

# Scheduled runs start Python with -I, which leaves the script folder off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wmm import APP_NAME, ROOT, VERSION  # noqa: E402
from wmm.agent import core  # noqa: E402

DATA_DIR = ROOT / "dati"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {VERSION}")
    parser.add_argument("--port", type=int, default=8765, help="local port of the web console")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--preview", action="store_true", help="read-only mode: actions are simulated")
    parser.add_argument("--run-schedule", type=int, metavar="ID", help="run a scheduled action and exit")
    parser.add_argument("--install", action="store_true", help="install to C:\\Program Files (needed for schedules)")
    parser.add_argument("--target", metavar="FOLDER", help="installation folder for --install")
    parser.add_argument("--auto-install", action="store_true",
                        help="install or update the protected copy in Program Files, then start it (used by start_wmm.bat)")
    parser.add_argument("--pause", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--wait-port", action="store_true", help=argparse.SUPPRESS)
    return parser


def wait_for_port(port: int, seconds: float = 15.0) -> None:
    """Used after "Restart as administrator": the old console frees the port a moment later."""
    import socket
    import time
    fine = time.monotonic() + seconds
    while time.monotonic() < fine:
        prova = socket.socket()
        try:
            prova.bind(("127.0.0.1", port))
            return
        except OSError:
            time.sleep(0.5)
        finally:
            prova.close()


def installed_target() -> Path:
    from wmm import installer
    return installer.default_target(os.environ)


def same_folder(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def restart_as_admin(*extra: str) -> bool:
    """Asks for elevation. True when the elevated copy started."""
    parametri = subprocess.list2cmdline([str(Path(__file__).resolve()), *sys.argv[1:], *extra])
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, parametri, str(ROOT), 1) > 32


def install(target: Optional[str]) -> int:
    from wmm import installer
    from wmm.agent import scheduler

    destinazione = Path(target) if target else installer.default_target(os.environ)
    print(f"Installing {APP_NAME} {VERSION} to {destinazione} ...")
    try:
        esito = installer.copy_program(ROOT, destinazione)
    except (OSError, ValueError) as errore:
        print(f"Installation failed: {errore}")
        return 1
    print("History and service backup copied." if esito["data_copied"] else "Existing history in the installation folder kept.")
    if not installer.harden(destinazione):
        print("Warning: the permissions of the installation folder could not be fully reset.")
    programma = scheduler.unprotected_paths(scheduler.program_paths(str(destinazione / "wmm.py")))
    python = scheduler.unprotected_paths(scheduler.python_paths(sys.executable))
    if programma:
        print("The installation folder is still writable by standard users: " + ", ".join(programma[:3]))
        print("Choose a folder under C:\\Program Files, which only administrators can change.")
        return 1
    print("Program folder protected: only administrators can change it.")
    if python:
        print(f"Warning: Python at {sys.executable} can be changed by standard users.")
        print("Install Python for all users (python.org installer > Customize > Install Python for all users)")
        print("and start the console with that Python, otherwise schedules stay disabled.")
    print(f"Start the console from: {destinazione / 'start_wmm.bat'}")
    print("Schedules created before the installation show 'Program moved': press Resync on each of them.")
    return 0


def run_schedule(schedule_id: int) -> int:
    from wmm.agent.jobs import JobManager
    from wmm.agent.scheduler import run_schedule as esegui
    from wmm.agent.store import Store

    store = Store(DATA_DIR / "wmm.db")
    return esegui(schedule_id, store, JobManager(store, core.machine_id()))


def serve(port: int, preview: bool, open_browser: bool) -> int:
    from wmm.agent import health
    from wmm.server.api import Agent, make_server

    controlli = health.run_checks(DATA_DIR, port, core.is_admin(), sys.executable, str(ROOT / "wmm.py"))
    health.print_report(controlli)
    if health.summary(controlli)["blocking"]:
        print("The console cannot start until the failed checks above are fixed.")
        return 1
    agent = Agent(DATA_DIR, preview=preview, admin=core.is_admin())
    agent.set_health(controlli)
    try:
        server = make_server(agent, port)
    except OSError as errore:
        print(f"Port {port} is not available ({errore}). Use --port to choose another one.")
        return 1
    # The token travels only in this link (never in the served page), so other local
    # processes cannot read it from the server.
    indirizzo = f"http://127.0.0.1:{agent.port}/#k={agent.token}"
    print(f"{APP_NAME} {VERSION}")
    print(f"Console: {indirizzo}")
    print("Keep this link private: it authorizes changes to this PC.")
    print("Mode: " + ("preview (no changes)" if preview else "administrator" if agent.admin else "read-only"))
    print("Close this window or press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(indirizzo)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argomenti: Optional[Sequence[str]] = None) -> int:
    opzioni = build_parser().parse_args(argomenti)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    os.chdir(ROOT)
    if opzioni.run_schedule is not None:
        return run_schedule(opzioni.run_schedule)
    if opzioni.wait_port:
        wait_for_port(opzioni.port)
    if opzioni.install:
        if not core.is_admin():
            # The elevated copy opens its own window: --pause keeps it readable.
            if restart_as_admin("--pause"):
                return 0
            print("Administrator rights are required to install.")
            return 1
        codice = install(opzioni.target)
        if opzioni.pause:
            input("\nPress Enter to close.")
        return codice
    if opzioni.auto_install and not opzioni.preview:
        destinazione = installed_target()
        if not same_folder(destinazione, ROOT):
            if not core.is_admin():
                if restart_as_admin():
                    return 0
                print("Administrator rights were not granted: the console opens read-only from this folder.")
                return serve(opzioni.port, False, not opzioni.no_browser)
            if install(str(destinazione)) == 0:
                # Hand over to the protected copy: schedules can only run from there.
                inoltrati = [a for a in (list(argomenti) if argomenti is not None else sys.argv[1:]) if a != "--auto-install"]
                print(f"Starting {destinazione / 'wmm.py'}")
                return subprocess.call([sys.executable, str(destinazione / "wmm.py"), *inoltrati])
            print("Installation failed: starting this copy instead.")
            return serve(opzioni.port, False, not opzioni.no_browser)
    if not opzioni.preview and not core.is_admin():
        if restart_as_admin():
            return 0
        print("Administrator rights were not granted: the console opens read-only.")
    return serve(opzioni.port, opzioni.preview, not opzioni.no_browser)


if __name__ == "__main__":
    sys.exit(main())
