"""Back to the last good configuration (2.8). Every check of Suspicious changes keeps a dated copy of the places programs
use to start and hide (one a day, 90 days). Choosing a day compares it with the PC as it is now and builds a plan:
each difference becomes one operation with its exact opposite (a Run value removed or put back, a startup file moved to
quarantine, a service start type, a scheduled task disabled, a hosts line, a proxy value, an antivirus exclusion). The
plan is shown first and only the operations ticked on the page run, after a restore point. The opposites are kept, so
"Undo the return" puts everything back. What cannot be rebuilt (a deleted service, task, file or extension, an
administrator) is listed for a manual check. The fixes run since that day that can be undone are listed as well."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import drift
from .tools import powershell_command

KEEP_DAYS = 90
RUN_KEYS = ("HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce", "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Run", "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
            "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run")
START_MODES = {"auto": "auto", "manual": "demand", "disabled": "disabled"}
EXCLUSION_KINDS = {"path": "ExclusionPath", "process": "ExclusionProcess", "extension": "ExclusionExtension"}
PROXY_DWORD = ("ProxyEnable",)


class GoodConfigError(ValueError):
    """No copy for that day, or nothing to do."""


# ---------- dated copies ----------

def _folder(data_dir: Path) -> Path:
    return Path(data_dir) / "drift_snapshots"


def save_snapshot(data_dir: Path, istantanea: Dict[str, Dict[str, str]], giorno: Optional[date] = None) -> Path:
    """One copy a day (the last check of the day wins); copies older than KEEP_DAYS are removed."""
    cartella = _folder(data_dir)
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / f"{(giorno or date.today()).isoformat()}.json"
    percorso.write_text(json.dumps(istantanea, ensure_ascii=False), encoding="utf-8")
    for vecchio in sorted(cartella.glob("????-??-??.json"))[:-KEEP_DAYS]:
        try:
            vecchio.unlink()
        except OSError:
            pass
    return percorso


def days(data_dir: Path) -> List[str]:
    return sorted((p.stem for p in _folder(data_dir).glob("????-??-??.json")), reverse=True)


def load(data_dir: Path, giorno: str) -> Dict[str, Dict[str, str]]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", giorno or ""):
        raise GoodConfigError("Choose a day.")
    try:
        dati = json.loads((_folder(data_dir) / f"{giorno}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GoodConfigError("There is no copy of the configuration for that day.") from None
    return {c: {str(k): str(v) for k, v in (dati.get(c) or {}).items()} for c in drift.CATEGORIES}


# ---------- the plan ----------

def _split_run(item: str):
    for chiave in RUN_KEYS:
        if item.startswith(chiave + "\\"):
            return chiave, item[len(chiave) + 1:]
    return None, None


def _op(category: str, item: str, text: str, do: dict, undo: dict) -> dict:
    ident = hashlib.sha1(json.dumps([category, item, do], sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {"id": ident, "category": category, "item": item, "text": text, "do": do, "undo": undo}


def _start_mode(valore: str) -> str:
    return (valore or "").split("|", 1)[0].strip().lower()


def _exclusion(item: str):
    tipo, _, valore = item.partition(": ")
    return (tipo, valore) if tipo in EXCLUSION_KINDS and valore else (None, None)


def build_plan(target: Dict[str, Dict[str, str]], adesso: Dict[str, Dict[str, str]], quarantine: str) -> dict:
    """The operations that bring the PC from `adesso` back to `target`, each with its opposite."""
    ops: List[dict] = []
    manuali: List[dict] = []
    diff = drift.compare(target, adesso)

    def manual(voce, motivo):
        manuali.append({"category": voce["category"], "item": voce["item"], "detail": voce.get("detail", ""), "reason": motivo})

    for voce in diff["added"]:  # present now, absent on the good day
        c, item, valore = voce["category"], voce["item"], voce.get("detail", "")
        if c == "run_keys":
            chiave, nome = _split_run(item)
            if chiave:
                ops.append(_op(c, item, f"Remove the startup value {nome}", {"kind": "remove_value", "path": chiave, "name": nome},
                               {"kind": "set_value", "path": chiave, "name": nome, "value": valore}))
                continue
        elif c == "startup_folders":
            nome = re.split(r"[\\/]", item)[-1]
            ops.append(_op(c, item, f"Move {nome} out of the startup folder (to quarantine)",
                           {"kind": "move_file", "from": item, "to": f"{quarantine}\\{nome}"}, {"kind": "move_file", "from": f"{quarantine}\\{nome}", "to": item}))
            continue
        elif c == "services":
            attuale = _start_mode(valore)
            if attuale in START_MODES and attuale != "disabled":
                ops.append(_op(c, item, f"Disable the new service {item}", {"kind": "set_start", "service": item, "mode": "disabled"},
                               {"kind": "set_start", "service": item, "mode": attuale}))
                continue
            if attuale == "disabled":
                continue
        elif c == "tasks":
            ops.append(_op(c, item, f"Disable the scheduled task {item}", {"kind": "disable_task", "path": item}, {"kind": "enable_task", "path": item}))
            continue
        elif c == "hosts":
            ops.append(_op(c, item, f"Remove the hosts line {item}", {"kind": "hosts_remove", "line": item}, {"kind": "hosts_add", "line": item}))
            continue
        elif c == "defender_exclusions":
            tipo, valore_x = _exclusion(item)
            if tipo:
                ops.append(_op(c, item, f"Remove the antivirus exclusion {item}", {"kind": "remove_exclusion", "type": tipo, "value": valore_x},
                               {"kind": "add_exclusion", "type": tipo, "value": valore_x}))
                continue
        manual(voce, "appeared after that day: check whether you installed it")
    for voce in diff["removed"]:  # absent now, present on the good day
        c, item, valore = voce["category"], voce["item"], voce.get("detail", "")
        if c == "run_keys":
            chiave, nome = _split_run(item)
            if chiave:
                ops.append(_op(c, item, f"Put back the startup value {nome}", {"kind": "set_value", "path": chiave, "name": nome, "value": valore},
                               {"kind": "remove_value", "path": chiave, "name": nome}))
                continue
        elif c == "hosts":
            ops.append(_op(c, item, f"Put back the hosts line {item}", {"kind": "hosts_add", "line": item}, {"kind": "hosts_remove", "line": item}))
            continue
        elif c == "defender_exclusions":
            tipo, valore_x = _exclusion(item)
            if tipo:
                ops.append(_op(c, item, f"Put back the antivirus exclusion {item}", {"kind": "add_exclusion", "type": tipo, "value": valore_x},
                               {"kind": "remove_exclusion", "type": tipo, "value": valore_x}))
                continue
        manual(voce, "removed after that day: it cannot be rebuilt from here")
    for voce in diff["changed"]:
        c, item, prima, ora = voce["category"], voce["item"], voce.get("before", ""), voce.get("detail", "")
        if c == "run_keys":
            chiave, nome = _split_run(item)
            if chiave:
                ops.append(_op(c, item, f"Put back the startup value {nome}", {"kind": "set_value", "path": chiave, "name": nome, "value": prima},
                               {"kind": "set_value", "path": chiave, "name": nome, "value": ora}))
                continue
        elif c == "services":
            vecchio, nuovo = _start_mode(prima), _start_mode(ora)
            percorso_cambiato = prima.split("|", 1)[-1].strip() != ora.split("|", 1)[-1].strip()
            if vecchio in START_MODES and nuovo in START_MODES and vecchio != nuovo:
                ops.append(_op(c, item, f"Put back the start type of {item} ({vecchio})", {"kind": "set_start", "service": item, "mode": vecchio},
                               {"kind": "set_start", "service": item, "mode": nuovo}))
            if percorso_cambiato:
                manual(voce, "the program of the service changed: check it")
            continue
        elif c == "proxy":
            ops.append(_op(c, item, f"Put back the proxy setting {item}", {"kind": "set_proxy", "name": item, "value": prima},
                           {"kind": "set_proxy", "name": item, "value": ora}))
            continue
        manual(voce, "changed after that day")
    return {"ops": ops, "manual": manuali}


def undoable_runs(runs: List[dict], giorno: str) -> List[dict]:
    """Fixes run after the chosen day whose registry changes can still be put back (History › Undo)."""
    return [{"id": r["id"], "action_id": r.get("action_id"), "started": r.get("started"), "undo_count": r.get("undo_count")}
            for r in runs if (r.get("started") or "") >= giorno and r.get("undo_count") and not r.get("undone")]


def plan(data_dir: Path, giorno: str, adesso: Optional[Dict[str, Dict[str, str]]] = None, runs: Optional[List[dict]] = None) -> dict:
    target = load(data_dir, giorno)
    corrente = adesso if adesso is not None else drift.snapshot()
    quarantena = str(Path(data_dir) / "quarantine" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    piano = build_plan(target, corrente, quarantena)
    return dict(piano, day=giorno, runs=undoable_runs(runs or [], giorno), quarantine=quarantena)


# ---------- running the operations ----------

APPLY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ops = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__OPS__')) | ConvertFrom-Json
$hosts = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
function Norm($s) { ($s -replace '\s+', ' ').Trim() }
$res = @(foreach ($o in $ops) {
  try {
    switch ($o.kind) {
      'set_value' { if (-not (Test-Path -LiteralPath $o.path)) { New-Item -Path $o.path -Force | Out-Null }
                    $t = if ("$($o.value)" -match '%') { 'ExpandString' } else { 'String' }
                    New-ItemProperty -LiteralPath $o.path -Name $o.name -Value "$($o.value)" -PropertyType $t -Force | Out-Null }
      'remove_value' { Remove-ItemProperty -LiteralPath $o.path -Name $o.name }
      'move_file' { $d = Split-Path -Parent $o.to; if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
                    Move-Item -LiteralPath $o.from -Destination $o.to }
      'set_start' { $r = & sc.exe config "$($o.service)" start= "$($o.mode)"; if ($LASTEXITCODE -ne 0) { throw ($r -join ' ') } }
      'disable_task' { $i = $o.path.LastIndexOf('\'); Disable-ScheduledTask -TaskPath $o.path.Substring(0, $i + 1) -TaskName $o.path.Substring($i + 1) | Out-Null }
      'enable_task' { $i = $o.path.LastIndexOf('\'); Enable-ScheduledTask -TaskPath $o.path.Substring(0, $i + 1) -TaskName $o.path.Substring($i + 1) | Out-Null }
      'hosts_remove' { $l = @(Get-Content -LiteralPath $hosts); $keep = @($l | Where-Object { (Norm $_) -ne (Norm $o.line) })
                       if ($keep.Count -eq $l.Count) { throw 'line not found' }; Set-Content -LiteralPath $hosts -Value $keep -Encoding ASCII }
      'hosts_add' { Add-Content -LiteralPath $hosts -Value $o.line -Encoding ASCII }
      'set_proxy' { $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
                    if ("$($o.value)" -eq '') { Remove-ItemProperty -LiteralPath $k -Name $o.name -ErrorAction SilentlyContinue }
                    elseif ($o.name -eq 'ProxyEnable') { New-ItemProperty -LiteralPath $k -Name $o.name -Value ([int]$o.value) -PropertyType DWord -Force | Out-Null }
                    else { New-ItemProperty -LiteralPath $k -Name $o.name -Value "$($o.value)" -PropertyType String -Force | Out-Null } }
      'remove_exclusion' { $p = @{}; $p[$o.param] = $o.value; Remove-MpPreference @p }
      'add_exclusion' { $p = @{}; $p[$o.param] = $o.value; Add-MpPreference @p }
      default { throw "unknown operation $($o.kind)" }
    }
    [ordered]@{ ok = $true; error = '' }
  } catch { [ordered]@{ ok = $false; error = "$($_.Exception.Message)" } }
})
[ordered]@{ results = $res } | ConvertTo-Json -Depth 4 -Compress
"""
KINDS = {"set_value", "remove_value", "move_file", "set_start", "disable_task", "enable_task", "hosts_remove", "hosts_add", "set_proxy",
         "remove_exclusion", "add_exclusion"}


def _valid(op: dict) -> bool:
    if op.get("kind") not in KINDS:
        return False
    if op["kind"] in ("set_value", "remove_value"):
        return op.get("path") in RUN_KEYS and bool(op.get("name"))
    if op["kind"] == "set_start":
        return op.get("mode") in START_MODES.values() or op.get("mode") in START_MODES
    if op["kind"] in ("remove_exclusion", "add_exclusion"):
        return op.get("type") in EXCLUSION_KINDS
    if op["kind"] == "set_proxy":
        return op.get("name") in ("ProxyEnable", "ProxyServer", "AutoConfigURL")
    return True


def _prepare(op: dict) -> dict:
    pronta = dict(op)
    if op["kind"] == "set_start":
        pronta["mode"] = START_MODES.get(op["mode"], op["mode"])
    if op["kind"] in ("remove_exclusion", "add_exclusion"):
        pronta["param"] = EXCLUSION_KINDS[op["type"]]
    return pronta


def run_ops(ops: List[dict], runner: Optional[Callable[[str], str]] = None) -> List[dict]:
    """Runs the operations in one PowerShell process; the values travel as base64 JSON, never inside the script text."""
    if not ops:
        return []
    if not all(_valid(o) for o in ops):
        raise GoodConfigError("An operation is not valid.")
    carico = base64.b64encode(json.dumps([_prepare(o) for o in ops], ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = APPLY_SCRIPT.replace("__OPS__", carico)
    if runner is None:
        finito = subprocess.run(powershell_command(script), capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        testo = finito.stdout
    else:
        testo = runner(script)
    righe = (testo or "").strip().splitlines()
    try:
        risultati = json.loads(righe[-1]).get("results") if righe else None
    except (ValueError, AttributeError):
        risultati = None
    if isinstance(risultati, dict):
        risultati = [risultati]
    if not isinstance(risultati, list) or len(risultati) != len(ops):
        return [{"ok": False, "error": "no answer from PowerShell"} for _ in ops]
    return [{"ok": bool(r.get("ok")), "error": str(r.get("error") or "")[:300]} for r in risultati]


def _last_path(data_dir: Path) -> Path:
    return Path(data_dir) / "goodconfig_last.json"


def apply(data_dir: Path, piano: dict, scelte: List[str], runner: Optional[Callable[[str], str]] = None) -> dict:
    """Runs the chosen operations of a plan just built (ids from the page, never operations from the page) and keeps
    the opposites of those that worked."""
    per_id = {o["id"]: o for o in piano["ops"]}
    scelti = [per_id[i] for i in scelte if i in per_id]
    if not scelti:
        raise GoodConfigError("Tick at least one change.")
    esiti = run_ops([o["do"] for o in scelti], runner)
    fatti = [dict(o, result=e) for o, e in zip(scelti, esiti)]
    riusciti = [o for o in fatti if o["result"]["ok"]]
    if riusciti:
        _last_path(data_dir).write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "day": piano["day"],
                                                    "ops": [{"text": o["text"], "undo": o["undo"]} for o in riusciti]}, ensure_ascii=False),
                                        encoding="utf-8")
    return {"done": len(riusciti), "failed": len(fatti) - len(riusciti),
            "results": [{"id": o["id"], "text": o["text"], "ok": o["result"]["ok"], "error": o["result"]["error"]} for o in fatti]}


def last(data_dir: Path) -> Optional[dict]:
    try:
        dati = json.loads(_last_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"at": dati.get("at"), "day": dati.get("day"), "count": len(dati.get("ops", [])), "undone": dati.get("undone")}


def revert(data_dir: Path, runner: Optional[Callable[[str], str]] = None) -> dict:
    """Undo the return: the opposites, newest first."""
    percorso = _last_path(data_dir)
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GoodConfigError("There is no return to undo.") from None
    if dati.get("undone"):
        raise GoodConfigError(f"Already undone on {dati['undone']}.")
    voci = list(reversed(dati.get("ops", [])))
    esiti = run_ops([v["undo"] for v in voci], runner)
    dati["undone"] = datetime.now().isoformat(timespec="seconds")
    percorso.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    return {"done": sum(1 for e in esiti if e["ok"]), "failed": sum(1 for e in esiti if not e["ok"]),
            "results": [{"text": v["text"], "ok": e["ok"], "error": e["error"]} for v, e in zip(voci, esiti)]}
