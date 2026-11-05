"""Software deployment with winget (2.10): install, update or remove a program of the company catalog on this PC, from
the console or as a job of the central server. Only real winget IDs (Publisher.Program), only from the winget source,
silent, with the agreements accepted on behalf of the organization that put the program in its catalog."""
from __future__ import annotations

import re
import subprocess
from typing import Callable, Optional

ID = re.compile(r"[A-Za-z0-9][\w\-+]*(\.[\w\-+]+)+")
OPS = ("install", "upgrade", "uninstall")


def valid_id(winget_id: str) -> bool:
    return bool(ID.fullmatch(winget_id or "")) and len(winget_id) <= 120


def command(op: str, winget_id: str) -> list:
    if op not in OPS or not valid_id(winget_id):
        raise ValueError("Unknown operation or winget ID.")
    base = ["winget", op, "--id", winget_id, "--exact", "--silent", "--disable-interactivity"]
    if op != "uninstall":
        base += ["--source", "winget", "--accept-package-agreements", "--accept-source-agreements"]
    return base


def run(op: str, winget_id: str, runner: Optional[Callable[[list], subprocess.CompletedProcess]] = None, preview: bool = False) -> dict:
    comando = command(op, winget_id)
    if preview:
        return {"op": op, "id": winget_id, "ok": True, "preview": True, "output": " ".join(comando)}
    try:
        r = (runner or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace",
                                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))))(comando)
    except FileNotFoundError:
        return {"op": op, "id": winget_id, "ok": False, "code": None, "output": "winget is not installed (App Installer from the Microsoft Store)."}
    except subprocess.TimeoutExpired:
        return {"op": op, "id": winget_id, "ok": False, "code": None, "output": "winget did not finish within 30 minutes."}
    testo = (r.stdout or "") + (r.stderr or "")
    righe = [x.strip() for x in testo.splitlines() if x.strip() and not re.fullmatch(r"[\-\\|/ ]+|[█▒ ]+.*", x.strip())]
    # 0 = done; -1978335189 = no applicable update (already current); -1978335135 = already installed
    ok = r.returncode in (0, -1978335189, -1978335135, 2316632107, 2316632161)
    return {"op": op, "id": winget_id, "ok": ok, "code": r.returncode, "output": "\n".join(righe[-15:])[:3000]}
