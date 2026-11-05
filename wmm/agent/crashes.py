"""Blue screens explained (2.8). Windows keeps a small dump for every stop error in C:\\Windows\\Minidump and logs the
event "The computer has rebooted from a bugcheck" in the System log. This reads the stop code straight from the dump
header (no debugger needed), explains it in plain words, and lists the drivers installed in the week before the first
crash of each kind: when a crash starts right after a driver arrived, that driver is the first suspect. Read-only."""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ottimizza_pc import Esito, Stato

from .tools import powershell_command

MINIDUMP_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Minidump"
MAX_DUMPS = 60

# Stop code -> name, what it usually means, what to do and the tools of the catalog that help. English text with an
# Italian copy: the page shows the one of the console language.
CODES: Dict[int, dict] = {}


def _code(numero, nome, cause, cause_it, fix, fix_it, tools=()):
    CODES[numero] = {"name": nome, "cause": cause, "cause_it": cause_it, "fix": fix, "fix_it": fix_it, "tools": list(tools)}


_code(0x0A, "IRQL_NOT_LESS_OR_EQUAL", "A driver touched memory it was not allowed to touch.",
      "Un driver ha usato memoria che non poteva usare.", "Update or roll back the drivers installed recently; then test the memory.",
      "Aggiorna o riporta indietro i driver installati di recente, poi prova la memoria.", ("updates.driver_scan", "updates.problem_devices"))
_code(0x1A, "MEMORY_MANAGEMENT", "Windows found damaged memory pages: often a faulty RAM module or an unstable overclock.",
      "Windows ha trovato pagine di memoria danneggiate: spesso un modulo RAM guasto o un overclock instabile.",
      "Run the Windows memory test, remove any overclock (XMP/EXPO), then check system files.",
      "Esegui il test della memoria di Windows, togli l'overclock (XMP/EXPO), poi controlla i file di sistema.", ("integrity.sfc",))
_code(0x3B, "SYSTEM_SERVICE_EXCEPTION", "A system call failed inside a driver, often graphics or antivirus.",
      "Una chiamata di sistema è fallita dentro un driver, spesso della scheda video o dell'antivirus.",
      "Update the graphics driver and the antivirus; check system files.", "Aggiorna il driver video e l'antivirus; controlla i file di sistema.",
      ("integrity.sfc", "updates.driver_scan"))
_code(0x50, "PAGE_FAULT_IN_NONPAGED_AREA", "A driver or a memory module returned invalid data.",
      "Un driver o un modulo di memoria ha restituito dati non validi.", "Test the memory and update the drivers installed recently.",
      "Prova la memoria e aggiorna i driver installati di recente.", ("updates.driver_scan",))
_code(0x7E, "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", "A driver raised an error that nothing handled.",
      "Un driver ha generato un errore che nessuno ha gestito.", "Update or remove the driver installed before the first crash.",
      "Aggiorna o rimuovi il driver installato prima del primo blocco.", ("updates.driver_scan", "updates.problem_devices"))
_code(0x1E, "KMODE_EXCEPTION_NOT_HANDLED", "A driver raised an error that nothing handled.", "Un driver ha generato un errore che nessuno ha gestito.",
      "Update or remove the driver installed before the first crash.", "Aggiorna o rimuovi il driver installato prima del primo blocco.",
      ("updates.driver_scan",))
_code(0x7F, "UNEXPECTED_KERNEL_MODE_TRAP", "The processor raised a trap the kernel could not handle: hardware or overclock.",
      "Il processore ha generato un'eccezione che il sistema non ha gestito: hardware o overclock.",
      "Remove any overclock, check temperatures and test the memory.", "Togli l'overclock, controlla le temperature e prova la memoria.",
      ("performance.thermal_report",))
_code(0x9F, "DRIVER_POWER_STATE_FAILURE", "A device did not answer when the PC went to sleep or woke up.",
      "Un dispositivo non ha risposto quando il PC andava in sospensione o si riattivava.",
      "Update chipset, network and USB drivers; turn off USB selective suspend.",
      "Aggiorna i driver di chipset, rete e USB; disattiva la sospensione selettiva USB.", ("performance.usb_suspend_off", "updates.driver_scan"))
_code(0xA0, "INTERNAL_POWER_ERROR", "The power manager failed, often while hibernating.",
      "La gestione dell'energia ha avuto un errore, spesso durante l'ibernazione.",
      "Update the BIOS and chipset drivers; try turning hibernation off and on again.",
      "Aggiorna BIOS e driver del chipset; prova a disattivare e riattivare l'ibernazione.", ("updates.driver_scan",))
_code(0x19, "BAD_POOL_HEADER", "Kernel memory was damaged, usually by a driver.", "La memoria del sistema è stata danneggiata, di solito da un driver.",
      "Update or remove the drivers installed recently.", "Aggiorna o rimuovi i driver installati di recente.", ("updates.driver_scan",))
_code(0xC2, "BAD_POOL_CALLER", "A driver used kernel memory the wrong way.", "Un driver ha usato la memoria del sistema in modo sbagliato.",
      "Update or remove the drivers installed recently.", "Aggiorna o rimuovi i driver installati di recente.", ("updates.driver_scan",))
_code(0xC5, "DRIVER_CORRUPTED_EXPOOL", "A driver damaged kernel memory.", "Un driver ha danneggiato la memoria del sistema.",
      "Update or remove the drivers installed recently.", "Aggiorna o rimuovi i driver installati di recente.", ("updates.driver_scan",))
_code(0x4E, "PFN_LIST_CORRUPT", "The list of memory pages was damaged: driver or RAM.", "L'elenco delle pagine di memoria è danneggiato: driver o RAM.",
      "Test the memory and update the drivers.", "Prova la memoria e aggiorna i driver.", ("updates.driver_scan",))
_code(0xD1, "DRIVER_IRQL_NOT_LESS_OR_EQUAL", "A driver (often network, Wi-Fi or USB) accessed invalid memory.",
      "Un driver (spesso di rete, Wi-Fi o USB) ha usato memoria non valida.", "Update the network and Wi-Fi drivers first.",
      "Aggiorna prima i driver di rete e Wi-Fi.", ("updates.driver_scan", "updates.problem_devices"))
_code(0xEF, "CRITICAL_PROCESS_DIED", "A process Windows needs stopped: damaged system files or disk.",
      "Si è fermato un processo indispensabile a Windows: file di sistema o disco danneggiati.",
      "Repair system files and the Windows image, then check the disk.", "Ripara i file di sistema e l'immagine di Windows, poi controlla il disco.",
      ("integrity.sfc", "integrity.dism", "integrity.disk_scan"))
_code(0xF4, "CRITICAL_OBJECT_TERMINATION", "A vital process ended, often because the disk stopped answering.",
      "Un processo vitale si è chiuso, spesso perché il disco non rispondeva.", "Check disk health and cables; update the storage driver.",
      "Controlla la salute del disco e i cavi; aggiorna il driver del disco.", ("storage.disk_health", "integrity.disk_scan"))
_code(0x7A, "KERNEL_DATA_INPAGE_ERROR", "Windows could not read data back from the disk: failing disk or cable.",
      "Windows non è riuscito a rileggere dati dal disco: disco o cavo guasto.", "Check disk health now and back up your files.",
      "Controlla subito la salute del disco e fai una copia dei tuoi file.", ("storage.disk_health", "storage.smart_prediction"))
_code(0x24, "NTFS_FILE_SYSTEM", "The file system found damage on the disk.", "Il file system ha trovato danni sul disco.",
      "Check and repair the disk.", "Controlla e ripara il disco.", ("integrity.disk_scan", "integrity.disk_repair"))
_code(0x133, "DPC_WATCHDOG_VIOLATION", "A driver kept the processor busy too long, often storage (SATA/NVMe) or graphics.",
      "Un driver ha tenuto occupato il processore troppo a lungo, spesso del disco (SATA/NVMe) o della scheda video.",
      "Update the SSD firmware and the storage and graphics drivers.", "Aggiorna il firmware dell'SSD e i driver del disco e della scheda video.",
      ("updates.driver_scan",))
_code(0x139, "KERNEL_SECURITY_CHECK_FAILURE", "A driver damaged a kernel structure; sometimes faulty memory.",
      "Un driver ha danneggiato una struttura del sistema; a volte memoria guasta.", "Update the drivers installed recently and test the memory.",
      "Aggiorna i driver installati di recente e prova la memoria.", ("updates.driver_scan", "integrity.sfc"))
_code(0x116, "VIDEO_TDR_FAILURE", "The graphics card stopped answering and could not be reset.",
      "La scheda video ha smesso di rispondere e non si è ripresa.",
      "Install the graphics driver from the maker's site, check GPU temperature, remove any GPU overclock.",
      "Installa il driver video dal sito del produttore, controlla la temperatura della scheda video, togli l'overclock.",
      ("performance.gpu_report", "performance.thermal_report"))
_code(0x117, "VIDEO_TDR_TIMEOUT_DETECTED", "The graphics card took too long to answer.", "La scheda video ha impiegato troppo a rispondere.",
      "Update the graphics driver and check its temperature.", "Aggiorna il driver video e controllane la temperatura.", ("performance.gpu_report",))
_code(0x124, "WHEA_UNCORRECTABLE_ERROR", "The hardware reported an error it could not correct: processor, memory, power supply or overclock.",
      "L'hardware ha segnalato un errore che non ha potuto correggere: processore, memoria, alimentatore o overclock.",
      "Remove any overclock, update the BIOS, check temperatures and the hardware error report.",
      "Togli l'overclock, aggiorna il BIOS, controlla le temperature e il rapporto degli errori hardware.",
      ("integrity.whea_report", "performance.thermal_report"))
_code(0x101, "CLOCK_WATCHDOG_TIMEOUT", "One processor core stopped answering: overclock, BIOS or a failing processor.",
      "Un core del processore ha smesso di rispondere: overclock, BIOS o processore guasto.", "Remove any overclock and update the BIOS.",
      "Togli l'overclock e aggiorna il BIOS.", ("performance.thermal_report",))
_code(0xC000021A, "STATUS_SYSTEM_PROCESS_TERMINATED", "A core Windows process ended: damaged system files or a bad update.",
      "Si è chiuso un processo centrale di Windows: file di sistema danneggiati o un aggiornamento difettoso.",
      "Repair system files and the Windows image; uninstall the last update if the crashes started after it.",
      "Ripara i file di sistema e l'immagine di Windows; disinstalla l'ultimo aggiornamento se i blocchi sono iniziati dopo.",
      ("integrity.sfc", "integrity.dism"))

UNKNOWN = {"name": "", "cause": "A stop error without a common explanation: look at the drivers installed before it.",
           "cause_it": "Un blocco senza una spiegazione comune: guarda i driver installati prima.",
           "fix": "Update the drivers listed as suspects and check system files.", "fix_it": "Aggiorna i driver sospetti e controlla i file di sistema.",
           "tools": ["integrity.sfc", "updates.driver_scan"]}


def read_dump_header(path: Path) -> Optional[dict]:
    """Stop code and its four parameters from a 64-bit (PAGEDU64) or 32-bit (PAGEDUMP) dump header."""
    try:
        with open(path, "rb") as file:
            testa = file.read(0x80)
    except OSError:
        return None
    if testa[:8] == b"PAGEDU64" and len(testa) >= 0x60:
        codice = struct.unpack_from("<I", testa, 0x38)[0]
        parametri = list(struct.unpack_from("<4Q", testa, 0x40))
    elif testa[:8] == b"PAGEDUMP" and len(testa) >= 0x54:
        codice = struct.unpack_from("<I", testa, 0x40)[0]
        parametri = list(struct.unpack_from("<4I", testa, 0x44))
    else:
        return None
    return {"code": codice, "params": parametri}


def explain(codice: int) -> dict:
    voce = CODES.get(codice, UNKNOWN)
    return dict(voce, code=f"0x{codice:08X}", name=voce["name"] or f"0x{codice:X}")


EVENTS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$d = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-UserPnp'; Id = 20001, 20003 } -MaxEvents 400 |
  ForEach-Object { [ordered]@{ at = $_.TimeCreated.ToString('s'); text = (($_.Message -split "`n")[0]).Trim() } })
$b = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 1001; ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting' } -MaxEvents 100 |
  ForEach-Object { [ordered]@{ at = $_.TimeCreated.ToString('s'); text = ($_.Message -replace '\s+', ' ').Trim() } })
[ordered]@{ drivers = $d; bugchecks = $b } | ConvertTo-Json -Depth 4 -Compress
"""


def run_json(script: str, runner: Optional[Callable[[], str]] = None, timeout: int = 120) -> dict:
    """Runs a read-only PowerShell script whose last line is JSON (runner replaces it in tests)."""
    if runner is None:
        try:
            finito = subprocess.run(powershell_command(script), capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                                    errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            testo = finito.stdout
        except (OSError, subprocess.SubprocessError):
            testo = ""
    else:
        testo = runner()
    righe = (testo or "").strip().splitlines()
    try:
        dati = json.loads(righe[-1]) if righe else {}
    except ValueError:
        dati = {}
    return dati if isinstance(dati, dict) else {}


def as_list(v) -> list:
    return v if isinstance(v, list) else [v] if isinstance(v, dict) else []


def _events(runner: Optional[Callable[[], str]]) -> dict:
    dati = run_json(EVENTS_SCRIPT, runner)

    def elenco(v):
        return [{"at": str(x.get("at") or ""), "text": str(x.get("text") or "")[:300]} for x in as_list(v) if isinstance(x, dict)]
    return {"drivers": elenco(dati.get("drivers")), "bugchecks": elenco(dati.get("bugchecks"))}


BUGCHECK_TEXT = re.compile(r"bugcheck was:\s*(0x[0-9a-fA-F]+)", re.I)


def parse_time(iso: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(iso)[:19])
    except (TypeError, ValueError):
        return None


def analyze(folder: Optional[Path] = None, runner: Optional[Callable[[], str]] = None, now: Optional[datetime] = None) -> dict:
    """Every stop error found (dumps first, the System log for crashes whose dump was deleted), grouped by stop code."""
    cartella = Path(folder) if folder else MINIDUMP_DIR
    adesso = now or datetime.now()
    crash: List[dict] = []
    try:
        dump = sorted(cartella.glob("*.dmp"), key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_DUMPS]
    except OSError:
        dump = []
    for percorso in dump:
        testa = read_dump_header(percorso)
        if testa is None:
            continue
        try:
            quando = datetime.fromtimestamp(percorso.stat().st_mtime)
        except OSError:
            continue
        crash.append({"at": quando.isoformat(timespec="seconds"), "code": testa["code"], "params": [f"0x{p:X}" for p in testa["params"]],
                      "file": percorso.name, "source": "dump"})
    eventi = _events(runner)
    for evento in eventi["bugchecks"]:
        trovato, quando = BUGCHECK_TEXT.search(evento["text"]), parse_time(evento["at"])
        if not trovato or quando is None:
            continue
        codice = int(trovato.group(1), 16) & 0xFFFFFFFF
        # The same crash has both a dump and an event a few minutes apart: keep only one.
        if any(c["code"] == codice and abs((parse_time(c["at"]) - quando).total_seconds()) < 900 for c in crash):
            continue
        crash.append({"at": quando.isoformat(timespec="seconds"), "code": codice, "params": [], "file": "", "source": "event"})
    crash.sort(key=lambda c: c["at"], reverse=True)
    gruppi: Dict[int, dict] = {}
    for c in crash:
        g = gruppi.setdefault(c["code"], dict(explain(c["code"]), count=0, first=c["at"], last=c["at"], crashes=[]))
        g["count"] += 1
        g["first"] = min(g["first"], c["at"])
        g["last"] = max(g["last"], c["at"])
        g["crashes"].append({k: c[k] for k in ("at", "params", "file", "source")})
    driver = [(d, parse_time(d["at"])) for d in eventi["drivers"]]
    for g in gruppi.values():
        primo = parse_time(g["first"])
        g["suspects"] = [d for d, t in driver if t is not None and primo is not None and primo - timedelta(days=7) <= t <= primo][:10]
        g["crashes"] = g["crashes"][:10]
    elenco = sorted(gruppi.values(), key=lambda g: (g["count"], g["last"]), reverse=True)
    limite = adesso - timedelta(days=30)
    return {"crashes": len(crash), "last_30_days": sum(1 for c in crash if (parse_time(c["at"]) or limite) > limite), "groups": elenco,
            "folder": str(cartella), "checked": adesso.isoformat(timespec="seconds")}


def bsod_explained(ctx) -> Esito:
    dati = analyze()
    if not dati["crashes"]:
        ctx.scrivi("No blue screen found: no dump in the Minidump folder and no bugcheck in the System log.")
        return Esito(Stato.OK, "no blue screens")
    for g in dati["groups"]:
        ctx.scrivi(f"{g['name']} ({g['code']}): {g['count']} times, last {g['last'].replace('T', ' ')}")
        ctx.scrivi(f"  Cause: {g['cause']}")
        ctx.scrivi(f"  What to do: {g['fix']}")
        for d in g["suspects"][:5]:
            ctx.scrivi(f"  Installed before the first crash ({d['at'].replace('T', ' ')}): {d['text'][:160]}")
    return Esito(Stato.AVVISO, f"{dati['crashes']} blue screens, {dati['last_30_days']} in the last 30 days")
