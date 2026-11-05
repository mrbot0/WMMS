"""Your own tools in the Toolbox. A custom tool is a PowerShell script with the same guarantees as the built-in ones:
an area and a risk (moderate and high ones ask first and make a restore point), an optional read-only check that is
read before and after it runs (with the value that means "healthy"), and an optional undo script that History can run
to put things back. They are stored in dati\\custom_tools.json and join the catalog as custom.<id>."""
from __future__ import annotations

import json
import re
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional

from ottimizza_pc import Esito, Stato

from . import actions, undo, verify
from .tools import powershell_command

PREFIX = "custom."
MAX_TOOLS = 100
MAX_SCRIPT = 20000
FIELDS = {"title": 80, "description": 300, "warning": 200, "check_label": 80, "healthy": 200}
_lock = threading.RLock()


class CustomToolError(ValueError):
    """A tool that cannot be saved as it is."""


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "custom_tools.json"


def load(data_dir: Path) -> List[dict]:
    try:
        dati = json.loads(_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(dati, list):
        return []
    return [t for t in dati if isinstance(t, dict) and re.fullmatch(r"[0-9a-f]{8}", str(t.get("id", "")))]


def _save(data_dir: Path, elenco: List[dict]) -> None:
    percorso = _path(data_dir)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(".tmp")
    temporaneo.write_text(json.dumps(elenco, ensure_ascii=False, indent=1), encoding="utf-8")
    temporaneo.replace(percorso)


def validate(dati: dict) -> dict:
    if not isinstance(dati, dict):
        raise CustomToolError("Send the tool as an object.")
    voce = {}
    for campo, massimo in FIELDS.items():
        valore = dati.get(campo, "") or ""
        if not isinstance(valore, str) or len(valore) > massimo:
            raise CustomToolError(f"{campo} must be text of at most {massimo} characters.")
        voce[campo] = valore.strip()
    if not voce["title"]:
        raise CustomToolError("Give the tool a name.")
    for campo in ("script", "check", "undo"):
        valore = dati.get(campo, "") or ""
        if not isinstance(valore, str) or len(valore) > MAX_SCRIPT:
            raise CustomToolError(f"The {campo} script must be at most {MAX_SCRIPT} characters.")
        voce[campo] = valore.replace("\r\n", "\n").strip()
    if not voce["script"]:
        raise CustomToolError("Write the PowerShell script the tool runs.")
    voce["area"] = dati.get("area") if dati.get("area") in actions.AREAS else "integrity"
    voce["kind"] = "report" if dati.get("kind") == "report" else "fix"
    voce["risk"] = dati.get("risk") if dati.get("risk") in actions.RISKS else "moderate"
    if voce["kind"] == "report":
        voce["risk"], voce["check"], voce["undo"], voce["healthy"] = "safe", "", "", ""
    try:
        voce["minutes"] = max(0.1, min(120.0, float(dati.get("minutes") or 1)))
    except (TypeError, ValueError):
        raise CustomToolError("The duration must be a number of minutes.") from None
    return voce


def _runner(voce: dict):
    def run(ctx) -> Esito:
        if voce["kind"] != "report" and not ctx.modifica(f"Run the custom tool {voce['title']}"):
            return Esito(Stato.ANTEPRIMA)
        if voce.get("undo"):
            # The undo script joins the journal of this run: History > Undo runs it.
            giornale = undo._journal()
            if giornale is not None:
                giornale.record_other("script", {"tool": voce["id"]}, voce["undo"])
        return ctx.comando(powershell_command(voce["script"]))
    return run


def action_of(voce: dict) -> actions.Action:
    return actions.Action(PREFIX + voce["id"], voce["area"], voce["title"], voce["description"] or "Custom tool.", voce["risk"],
                          voce["minutes"], _runner(voce), voce.get("warning", ""), voce["kind"])


def register(data_dir: Path) -> int:
    """Puts the custom tools in the catalog (and their checks in verify), replacing the previous ones."""
    with _lock:
        for chiave in [k for k in actions.CATALOG if k.startswith(PREFIX)]:
            del actions.CATALOG[chiave]
            verify.CHECKS.pop(chiave, None)
        elenco = load(data_dir)
        for voce in elenco:
            azione = action_of(voce)
            actions.CATALOG[azione.id] = azione
            if voce["kind"] == "fix" and voce.get("check"):
                atteso = voce.get("healthy", "")
                verify.CHECKS[azione.id] = verify.Check(voce.get("check_label") or "Custom check", voce["check"],
                                                        (lambda valore, a=atteso: valore.strip() == a) if atteso else None)
        return len(elenco)


def save(data_dir: Path, dati: dict, tool_id: Optional[str] = None) -> dict:
    voce = validate(dati)
    with _lock:
        elenco = load(data_dir)
        if tool_id:
            indice = next((i for i, t in enumerate(elenco) if t["id"] == tool_id), None)
            if indice is None:
                raise KeyError(tool_id)
            voce["id"] = tool_id
            elenco[indice] = voce
        else:
            if len(elenco) >= MAX_TOOLS:
                raise CustomToolError(f"At most {MAX_TOOLS} custom tools.")
            voce["id"] = secrets.token_hex(4)
            elenco.append(voce)
        _save(data_dir, elenco)
        register(data_dir)
    return voce


def delete(data_dir: Path, tool_id: str) -> None:
    with _lock:
        elenco = load(data_dir)
        rimasti = [t for t in elenco if t["id"] != tool_id]
        if len(rimasti) == len(elenco):
            raise KeyError(tool_id)
        _save(data_dir, rimasti)
        register(data_dir)


# ---------- the undo journal learns to run an undo script ----------

def _default_run_script(script: str) -> None:
    finito = subprocess.run(powershell_command(script), capture_output=True, text=True, timeout=600,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), encoding="utf-8", errors="replace")
    if finito.returncode != 0:
        raise OSError((finito.stderr or finito.stdout or f"exit code {finito.returncode}").strip()[-300:])


RUN_SCRIPT = _default_run_script


def _run_undo_script(voce: dict) -> None:
    RUN_SCRIPT(voce.get("value") or "")


# A script has no "after" reading: once the tool ran, its undo is always worth offering.
undo.OTHER_READERS["script"] = lambda voce: None
undo.OTHER_RESTORERS["script"] = _run_undo_script


def public(data_dir: Path) -> Dict[str, object]:
    return {"tools": load(data_dir), "areas": list(actions.AREAS), "risks": list(actions.RISKS), "max": MAX_TOOLS}
