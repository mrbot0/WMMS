"""Real tests of the fixes in Windows Sandbox. The parser, the preview and the read-only checks never run a fix for
real; this does, in a throw-away Windows that disappears when it closes, so this PC is never touched.

Host side (python wmm.py --sandbox-test [--only id,id] [--quick]):
  writes dati\\sandbox\\test.wsb, which maps this folder and the Python install read-only and an output folder
  read-write, starts Windows Sandbox and waits for the results.
Sandbox side (python wmm\\sandbox.py --run), started by the .wsb at sign-in:
  runs every selected fix (out\\ids.txt) through the normal job runner, so the before/after check and the registry
  journal work as they do on a real PC, then tries the precise undo of each fix and checks that every value came back.
Results are written after every fix to out\\results.json, so a crash or a timeout keeps what was done."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOX_REPO, BOX_PYTHON, BOX_OUT = r"C:\wmm", r"C:\py", r"C:\out"
IDS_FILE = "ids.txt"
# Fixes that restart Windows right away would end the Sandbox in the middle of the run.
EXCLUDED = frozenset({"security.offline_scan"})
QUICK_MINUTES = 5
DEFAULT_TIMEOUT_MINUTES = 240


def sandbox_exe() -> Optional[str]:
    trovato = shutil.which("WindowsSandbox.exe")
    if trovato:
        return trovato
    candidato = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
    return str(candidato) if candidato.is_file() else None


def select(catalog: dict, only: Iterable[str] = (), quick: bool = False) -> List[str]:
    """The fixes to run: the ones asked for, else every fix (reports change nothing and are not worth a Sandbox)."""
    scelti = [a.strip() for a in only if a.strip()]
    sconosciuti = [a for a in scelti if a not in catalog]
    if sconosciuti:
        raise KeyError(", ".join(sconosciuti))
    if scelti:
        return scelti
    return [a.id for a in catalog.values() if a.kind != "report" and a.id not in EXCLUDED and (not quick or a.minutes <= QUICK_MINUTES)]


def config(repo: Path, python_home: Path, out: Path, close: bool = True) -> str:
    """The .wsb file. Networking stays on for the fixes that download (Defender signatures, winget, Store)."""
    comando = (f'cmd /c "{BOX_PYTHON}\\python.exe -B -X utf8 {BOX_REPO}\\wmm\\sandbox.py --run --out {BOX_OUT}'
               f'{" --close" if close else ""} > {BOX_OUT}\\runner.log 2>&1"')
    cartelle = [(repo, BOX_REPO, True), (python_home, BOX_PYTHON, True), (out, BOX_OUT, False)]
    mappe = "".join(
        f"    <MappedFolder><HostFolder>{escape(str(h))}</HostFolder><SandboxFolder>{escape(s)}</SandboxFolder>"
        f"<ReadOnly>{'true' if ro else 'false'}</ReadOnly></MappedFolder>\n" for h, s, ro in cartelle)
    return ("<Configuration>\n  <VGpu>Disable</VGpu>\n  <Networking>Enable</Networking>\n  <ClipboardRedirection>Disable</ClipboardRedirection>\n"
            "  <PrinterRedirection>Disable</PrinterRedirection>\n  <MemoryInMB>4096</MemoryInMB>\n"
            f"  <MappedFolders>\n{mappe}  </MappedFolders>\n  <LogonCommand><Command>{escape(comando)}</Command></LogonCommand>\n</Configuration>\n")


def summary(risultati: List[dict]) -> dict:
    conta: dict = {}
    verdetti: dict = {}
    for r in risultati:
        conta[r["status"]] = conta.get(r["status"], 0) + 1
        v = (r.get("verify") or {}).get("verdict")
        if v:
            verdetti[v] = verdetti.get(v, 0) + 1
    annulli = [r for r in risultati if r.get("undo_count")]
    return {"total": len(risultati), "by_status": conta, "by_verdict": verdetti,
            "undo_tested": len(annulli), "undo_failed": [r["action_id"] for r in annulli if r.get("undo_ok") is False],
            "failed": [r["action_id"] for r in risultati if r["status"] == "error"],
            "not_fixed": [r["action_id"] for r in risultati if (r.get("verify") or {}).get("verdict") in ("not_fixed", "worse")]}


def _write(out: Path, risultati: List[dict], finito: bool) -> None:
    dati = {"updated": datetime.now().isoformat(timespec="seconds"), "finished": finito, "results": risultati, "summary": summary(risultati)}
    temporaneo = out / "results.tmp"
    temporaneo.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporaneo, out / "results.json")


# ---------- inside the Sandbox ----------

def _same_as_before(voce: dict, adesso) -> bool:
    from wmm.agent import undo
    if not voce.get("existed"):
        return adesso is None
    return adesso is not None and list(undo.encode(*adesso)) == [voce.get("type"), voce.get("value")]


def run_inside(out: Path, ids: List[str], manager=None, reader=None) -> List[dict]:
    """Runs each fix for real with the normal job runner, then its precise undo, writing the results after each one."""
    from ottimizza_pc import Esito, Stato
    from wmm.agent import actions, jobs, undo
    from wmm.agent.store import Store

    out.mkdir(parents=True, exist_ok=True)
    leggi = reader or undo.read_value
    if manager is None:
        # Windows Sandbox has no System Restore: the restore point before risky fixes is skipped, not a reason to stop.
        jobs.op.punto_ripristino = lambda ctx: Esito(Stato.SALTATO, "Windows Sandbox has no restore points")
        manager = jobs.JobManager(Store(out / "sandbox.db"), "SANDBOX")
    risultati: List[dict] = []
    for action_id in ids:
        inizio = time.monotonic()
        azione = actions.CATALOG.get(action_id)
        voce = {"action_id": action_id, "title": azione.title if azione else action_id, "risk": azione.risk if azione else ""}
        try:
            job = manager.run_sync([action_id], "sandbox", True)
            r = job["results"][0] if job["results"] else {"status": "error", "note": "no result"}
            voce.update(status=r["status"], note=r.get("note", ""), verify=r.get("verify"), undo_count=r.get("undo_count", 0), log=job["log"][-40:])
            if r.get("undo_count") and r.get("run_id"):
                voci = manager.store.run_undo(r["run_id"])["entries"]
                esito = manager.undo_run(r["run_id"])
                tornati = [v for v in voci if _same_as_before(v, leggi(v["root"], v["key"], v["name"]))]
                voce.update(undo_restored=esito["restored"], undo_errors=esito["errors"], undo_ok=len(tornati) == len(voci))
        except Exception as errore:  # one broken fix must not stop the test of the others
            voce.update(status="error", note=f"{type(errore).__name__}: {errore}")
        voce["seconds"] = round(time.monotonic() - inizio, 1)
        risultati.append(voce)
        _write(out, risultati, False)
    _write(out, risultati, True)
    return risultati


# ---------- on this PC ----------

def prepare(ids: List[str], data_dir: Optional[Path] = None, close: bool = True) -> Path:
    """The Sandbox folder with test.wsb, an empty out folder and the list of fixes to run. Returns the .wsb path."""
    cartella = Path(data_dir or ROOT / "dati") / "sandbox"
    out = cartella / "out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / IDS_FILE).write_text("\n".join(ids) + "\n", encoding="utf-8")
    wsb = cartella / "test.wsb"
    wsb.write_text(config(ROOT, Path(sys.base_prefix), out, close), encoding="utf-8")
    return wsb


def launch(only: Iterable[str] = (), quick: bool = False, wait: bool = True, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
           data_dir: Optional[Path] = None, starter=None, poll: float = 5.0) -> int:
    from wmm.agent import actions
    eseguibile = sandbox_exe()
    if eseguibile is None and starter is None:
        print("Windows Sandbox is not turned on on this PC. It needs Windows 10/11 Pro, Enterprise or Education with virtualization on.\n"
              "Turn it on from an administrator PowerShell, then restart:\n"
              "  Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All\n"
              "or from Settings > System > Optional features > More Windows features > Windows Sandbox.")
        return 2
    try:
        ids = select(actions.CATALOG, only, quick)
    except KeyError as errore:
        print(f"Unknown tools: {errore}")
        return 2
    wsb = prepare(ids, data_dir)
    print(f"{len(ids)} fixes will run for real in Windows Sandbox. Configuration: {wsb}")
    (starter or (lambda percorso: subprocess.Popen([eseguibile, str(percorso)])))(wsb)
    if not wait:
        return 0
    risultati = wsb.parent / "out" / "results.json"
    fine = time.monotonic() + timeout_minutes * 60
    ultimo = -1
    while time.monotonic() < fine:
        dati = _read(risultati)
        if dati:
            fatti = len(dati["results"])
            if fatti != ultimo:
                ultimo = fatti
                print(f"  {fatti}/{len(ids)}  {dati['results'][-1]['action_id'] if fatti else ''}")
            if dati.get("finished"):
                return report(dati, wsb.parent)
        time.sleep(poll)
    print(f"No final result within {timeout_minutes} minutes. Partial results: {risultati}")
    dati = _read(risultati)
    return report(dati, wsb.parent) if dati else 1


def _read(percorso: Path) -> Optional[dict]:
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def report(dati: dict, cartella: Path) -> int:
    s = dati["summary"]
    righe = [f"Windows Sandbox test, {dati['updated']}: {s['total']} fixes",
             "Results: " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_status"].items())),
             "Checks: " + (", ".join(f"{k} {v}" for k, v in sorted(s["by_verdict"].items())) or "none"),
             f"Precise undo tested on {s['undo_tested']} fixes, failed on {len(s['undo_failed'])}"]
    for titolo, elenco in (("Failed", s["failed"]), ("Check says not fixed", s["not_fixed"]), ("Undo did not restore everything", s["undo_failed"])):
        if elenco:
            righe.append(f"{titolo}: " + ", ".join(elenco))
    testo = "\n".join(righe)
    (cartella / "report.txt").write_text(testo + "\n", encoding="utf-8")
    print(testo)
    print(f"Details: {cartella / 'out' / 'results.json'}")
    return 1 if s["failed"] or s["undo_failed"] else 0


def main(argomenti: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixes for real in Windows Sandbox")
    parser.add_argument("--run", action="store_true", help="inside the Sandbox: run the fixes listed in out\\ids.txt")
    parser.add_argument("--out", default=BOX_OUT)
    parser.add_argument("--close", action="store_true", help="shut the Sandbox down when finished")
    parser.add_argument("--only", default="", help="comma-separated tool IDs (default: every fix)")
    parser.add_argument("--quick", action="store_true", help=f"only fixes that take up to {QUICK_MINUTES} minutes")
    parser.add_argument("--no-wait", action="store_true")
    opzioni = parser.parse_args(argomenti)
    if opzioni.run:
        out = Path(opzioni.out)
        ids = [r.strip() for r in (out / IDS_FILE).read_text(encoding="utf-8").splitlines() if r.strip()]
        run_inside(out, ids)
        if opzioni.close:
            subprocess.call(["shutdown", "/s", "/t", "15"])
        return 0
    return launch(opzioni.only.split(","), opzioni.quick, not opzioni.no_wait)


if __name__ == "__main__":
    sys.exit(main())
