"""Execution context and machine identity shared by the agent modules."""
from __future__ import annotations

import ctypes
import os
import re
import socket
import subprocess
from typing import Callable, Sequence

import wmm  # noqa: F401  (puts ottimizza_pc on sys.path)
import ottimizza_pc as op
from ottimizza_pc import Esito, Stato

STATUS = {
    Stato.OK: "ok",
    Stato.AVVISO: "warning",
    Stato.ERRORE: "error",
    Stato.SALTATO: "skipped",
    Stato.ANTEPRIMA: "preview",
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# ottimizza_pc speaks Italian; the console is in English.
_MESSAGES = (
    (re.compile(r"\[anteprima\]"), "[preview]"),
    (re.compile(r"\[gia' ok\]"), "[already set]"),
    (re.compile(r"\[fatto\]"), "[done]"),
    (re.compile(r"\[errore\]"), "[error]"),
    (re.compile(r"\[assente\]"), "[not installed]"),
    (re.compile(r"(\d+) file in uso lasciati"), r"\1 files in use were skipped"),
    (re.compile(r"(\d+) modificati, (\d+) non modificabili"), r"\1 changed, \2 could not be changed"),
    (re.compile(r"^(\d+) modificati$"), r"\1 changed"),
    (re.compile(r"(\d+) non ripristinati"), r"\1 not restored"),
    (re.compile(r"nessun servizio da ripristinare"), "no services to restore"),
    (re.compile(r"tutti ripristinati"), "all restored"),
    (re.compile(r"punto del "), "restore point of "),
    (re.compile(r"riparazione al prossimo riavvio"), "repair scheduled for the next restart"),
    (re.compile(r"vedi (\S+)"), r"see \1"),
    (re.compile(r"codice di uscita (\d+)"), r"exit code \1"),
    (re.compile(r"tempo scaduto"), "timed out"),
    (re.compile(r"nessun punto di ripristino disponibile"), "no restore point available"),
    (re.compile(r"ultimo punto di ripristino troppo vecchio"), "the latest restore point is too old"),
    (re.compile(r"Servizio protetto"), "Protected service"),
    (re.compile(r"Svuota cache Ottimizzazione recapito"), "Clear Delivery Optimization cache"),
    (re.compile(r"Svuota il Cestino"), "Empty the Recycle Bin"),
    (re.compile(r"Crea punto di ripristino"), "Create a restore point"),
    (re.compile(r"Elimina (\d+) dump"), r"Delete \1 dumps"),
    (re.compile(r"Servizio (\S+): "), r"Service \1: "),
)


def translate(testo: str) -> str:
    for schema, sostituto in _MESSAGES:
        testo = schema.sub(sostituto, testo)
    return testo


class JobContext(op.Contesto):
    """Context of ottimizza_pc that sends every output line to a callback."""

    def __init__(self, log: Callable[[str], None], preview: bool = False):
        super().__init__(preview)
        self._log = log

    def scrivi(self, testo: str = "") -> None:
        for riga in _ANSI.sub("", testo).splitlines() or [""]:
            self._log(translate(riga))

    def modifica(self, descrizione: str) -> bool:
        if self.anteprima:
            self.scrivi(f"  [preview] {translate(descrizione)}")
            return False
        self.registra(descrizione)
        return True

    def comando(self, comando: Sequence[str], validi: Sequence[int] = (0,)) -> Esito:
        testo = subprocess.list2cmdline(comando)
        if not self.modifica(testo):
            return Esito(Stato.ANTEPRIMA)
        self.scrivi(f"> {testo}")
        codifica = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        try:
            processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except OSError as errore:
            return Esito(Stato.ERRORE, str(errore))
        assert processo.stdout is not None
        resto = ""
        while True:
            blocco = os.read(processo.stdout.fileno(), 4096)
            if not blocco:
                break
            # sfc writes UTF-16 when redirected; progress lines end with \r.
            resto += blocco.replace(b"\x00", b"").decode(codifica, "replace")
            *righe, resto = re.split(r"\r\n|\r|\n", resto)
            for riga in righe:
                if riga.strip():
                    self._log(riga)
        if resto.strip():
            self._log(resto)
        codice = processo.wait()
        self.registra(f"codice uscita {codice}: {testo}")
        if codice in validi:
            return Esito(Stato.OK)
        return Esito(Stato.AVVISO, f"exit code {codice}")


def machine_id() -> str:
    host = socket.gethostname().upper()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as chiave:
            guid = winreg.QueryValueEx(chiave, "MachineGuid")[0]
        return f"{host}-{guid}"
    except OSError:
        return host


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False
