"""Ottimizza PC: manutenzione di Windows con passaggi eseguibili in sequenza.

Uso:
  python ottimizza_pc.py                      menu interattivo
  python ottimizza_pc.py --anteprima          menu senza modifiche al sistema
  python ottimizza_pc.py --elenco             elenca passaggi e sequenze pronte
  python ottimizza_pc.py --esegui 2 3 7-9     esegue i passaggi nell'ordine dato
  python ottimizza_pc.py --sequenza completa  esegue una sequenza pronta
  aggiungere --si per non ricevere domande di conferma

I servizi vengono disattivati, mai cancellati: lo stato originale viene salvato
prima di ogni modifica e si ripristina con il passaggio dedicato.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

CARTELLA = Path(__file__).resolve().parent
DATI = CARTELLA / "dati"
BACKUP_SERVIZI = DATI / "servizi-backup.json"
REGISTRO = DATI / "registro.txt"

GIORNI_FILE_VECCHI = 3
SOGLIA_SPAZIO_LIBERO = 15
SOGLIA_RAM_LIBERA = 10

SERVIZI_SICURI = (
    "DiagTrack", "dmwappushservice", "MapsBroker", "lfsvc", "RetailDemo",
    "WMPNetworkSvc", "Fax", "TrkWks", "SysMain", "WalletService", "PhoneSvc",
)
SERVIZI_MANUALI = ("AorusLcdService", "AsusCertService", "Razer Game Manager Service 3")
SERVIZI_XBOX = (
    "XblAuthManager", "XblGameSave", "XboxNetApiSvc", "XboxService",
    "GamingServices", "GamingServicesNet",
)
SERVIZI_STAMPA = ("Spooler", "stisvc")

# Il tool non deve mai modificare questi servizi.
SERVIZI_PROTETTI = frozenset({
    "WinDefend", "MDCoreSvc", "WdNisSvc", "SecurityHealthService", "mpssvc",
    "wuauserv", "BITS", "UsoSvc", "WerSvc", "EventLog", "RpcSs", "DcomLaunch",
    "WSLService", "LxssManager", "vmcompute", "vmms", "HvHost", "CoworkVMService",
    "vgc", "vgk", "NVDisplay.ContainerLocalSystem", "NvContainerLocalSystem",
    "Audiosrv", "AudioEndpointBuilder", "RtkAudioUniversalService", "NahimicService",
    "ElgatoLLMService", "WlanSvc", "Dhcp", "Dnscache", "BDESVC",
})

CARTELLE_PULIZIA = (
    "%TEMP%",
    r"C:\Windows\Temp",
    r"C:\Windows\SoftwareDistribution\Download",
    r"%LOCALAPPDATA%\D3DSCache",
    r"%LOCALAPPDATA%\NVIDIA\DXCache",
    r"%LOCALAPPDATA%\NVIDIA\GLCache",
    r"%LOCALAPPDATA%\CrashDumps",
)
ESCLUSI_PULIZIA = ("claude",)
CARTELLE_DUMP = (r"C:\Windows\LiveKernelReports", r"C:\Windows\Minidump")

CHIAVE_AVVIO_RAPIDO = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
CHIAVE_GAME_CONFIG = r"System\GameConfigStore"
CHIAVE_GAME_DVR = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"

CF_ANSI = {"ok": "32", "avviso": "33", "errore": "31", "titolo": "36;1", "tenue": "90"}


class Stato(Enum):
    OK = "OK"
    AVVISO = "AVVISO"
    ERRORE = "ERRORE"
    SALTATO = "SALTATO"
    ANTEPRIMA = "ANTEPRIMA"


@dataclass
class Esito:
    stato: Stato
    nota: str = ""


class SequenzaFermata(Exception):
    """Un passaggio di sicurezza e' fallito: i successivi non devono partire."""


def colore(testo: str, tipo: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return testo
    return f"\033[{CF_ANSI[tipo]}m{testo}\033[0m"


def dimensione(byte: float) -> str:
    valore = float(byte)
    for unita in ("B", "KB", "MB", "GB"):
        if abs(valore) < 1024:
            return f"{valore:.0f} {unita}" if unita in ("B", "KB") else f"{valore:.1f} {unita}"
        valore /= 1024
    return f"{valore:.1f} TB"


def durata(secondi: float) -> str:
    minuti, resto = divmod(int(secondi), 60)
    return f"{minuti}m {resto:02d}s" if minuti else f"{resto}s"


# ---------- Funzioni pure ----------

def leggi_avvio_servizio(uscita_sc_qc: str) -> Optional[str]:
    """Converte l'output di `sc qc` nel valore accettato da `sc config start=`."""
    trovato = re.search(r"START_TYPE\s*:\s*(\d+)\s+\S+(\s+\(DELAYED\))?", uscita_sc_qc)
    if not trovato:
        return None
    if trovato.group(1) == "2":
        return "delayed-auto" if trovato.group(2) else "auto"
    return {"3": "demand", "4": "disabled"}.get(trovato.group(1))


def servizio_attivo(uscita_sc_query: str) -> bool:
    return re.search(r"STATE\s*:\s*4\b", uscita_sc_query) is not None


def statistiche_ping(tempi: Sequence[float], inviati: int) -> Dict[str, float]:
    ricevuti = len(tempi)
    if not ricevuti:
        return {"media": 0.0, "massimo": 0.0, "jitter": 0.0, "persi": float(inviati)}
    salti = [abs(tempi[i] - tempi[i - 1]) for i in range(1, ricevuti)]
    return {
        "media": round(sum(tempi) / ricevuti, 1),
        "massimo": float(max(tempi)),
        "jitter": round(sum(salti) / len(salti), 1) if salti else 0.0,
        "persi": float(inviati - ricevuti),
    }


def come_lista(valore: object) -> list:
    if valore is None:
        return []
    return valore if isinstance(valore, list) else [valore]


def trova_problemi(dati: dict) -> List[str]:
    """Trasforma i dati del check-up in un elenco di problemi da affrontare."""
    problemi: List[str] = []
    memoria = dati.get("memoria") or {}
    if memoria.get("totaleGB") and 100 * memoria.get("liberaGB", 0) / memoria["totaleGB"] < SOGLIA_RAM_LIBERA:
        problemi.append(f"RAM libera sotto il {SOGLIA_RAM_LIBERA}%.")
    for disco in come_lista(dati.get("dischi")):
        nome = disco.get("nome", "?")
        if disco.get("salute") != "Healthy":
            problemi.append(f"Disco {nome} non sano ({disco.get('salute')}).")
        if (disco.get("usura") or 0) >= 80:
            problemi.append(f"SSD {nome} usurato al {disco['usura']}%.")
        if (disco.get("erroriLettura") or 0) > 0:
            problemi.append(f"Errori di lettura non corretti su {nome}.")
    for volume in come_lista(dati.get("volumi")):
        if volume.get("totaleGB") and 100 * volume.get("liberoGB", 0) / volume["totaleGB"] < SOGLIA_SPAZIO_LIBERO:
            problemi.append(f"Volume {volume.get('lettera')}: sotto il {SOGLIA_SPAZIO_LIBERO}% di spazio libero.")
    stabilita = dati.get("stabilita") or {}
    if stabilita.get("spegnimenti"):
        problemi.append(f"{stabilita['spegnimenti']} spegnimenti non puliti in 30 giorni.")
    if stabilita.get("whea"):
        problemi.append(f"{stabilita['whea']} errori hardware WHEA in 30 giorni.")
    if stabilita.get("disco"):
        problemi.append(f"{stabilita['disco']} errori disco in 30 giorni.")
    sistema = dati.get("sistema") or {}
    if (sistema.get("etaBiosGiorni") or 0) > 730:
        problemi.append("BIOS piu' vecchio di 2 anni: valuta un aggiornamento.")
    sicurezza = dati.get("sicurezza") or {}
    if sicurezza.get("defender") is False:
        problemi.append("Protezione in tempo reale di Defender disattivata.")
    if sicurezza.get("firewallSpenti"):
        problemi.append("Firewall disattivato su almeno un profilo.")
    if dati.get("riavvioInSospeso"):
        problemi.append("Riavvio in sospeso.")
    return problemi


def leggi_selezione(testo: str, identificativi: Sequence[int]) -> List[int]:
    """Legge `2 3,7-9` mantenendo l'ordine e togliendo i doppioni."""
    validi = set(identificativi)
    scelta: List[int] = []
    for parte in re.split(r"[\s,;]+", testo.strip()):
        if not parte:
            continue
        intervallo = re.fullmatch(r"(\d+)-(\d+)", parte)
        if intervallo:
            inizio, fine = int(intervallo.group(1)), int(intervallo.group(2))
            passo = 1 if fine >= inizio else -1
            numeri = list(range(inizio, fine + passo, passo))
        elif parte.isdigit():
            numeri = [int(parte)]
        else:
            raise ValueError(f"Non capisco '{parte}'.")
        for numero in numeri:
            if numero not in validi:
                raise ValueError(f"Il passaggio {numero} non esiste.")
            if numero not in scelta:
                scelta.append(numero)
    if not scelta:
        raise ValueError("Nessun passaggio selezionato.")
    return scelta


def file_da_pulire(radice: str, limite: float, esclusi: Sequence[str] = ESCLUSI_PULIZIA) -> Iterator[Tuple[str, int]]:
    """Elenca i file piu' vecchi di `limite` senza seguire collegamenti."""
    bloccati = {nome.lower() for nome in esclusi}
    for cartella, sottocartelle, file in os.walk(radice, followlinks=False):
        sottocartelle[:] = [
            nome for nome in sottocartelle
            if nome.lower() not in bloccati and not _e_collegamento(os.path.join(cartella, nome))
        ]
        for nome in file:
            percorso = os.path.join(cartella, nome)
            try:
                info = os.lstat(percorso)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_mtime < limite:
                yield percorso, info.st_size


def _e_collegamento(percorso: str) -> bool:
    try:
        info = os.lstat(percorso)
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


# ---------- Contesto di esecuzione ----------

class Contesto:
    def __init__(self, anteprima: bool = False):
        self.anteprima = anteprima
        self.riavvio_necessario = False
        DATI.mkdir(parents=True, exist_ok=True)

    def registra(self, testo: str) -> None:
        with REGISTRO.open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {testo}\n")

    def scrivi(self, testo: str = "") -> None:
        print(testo)

    def modifica(self, descrizione: str) -> bool:
        """Mostra l'azione in anteprima; restituisce True se va eseguita davvero."""
        if self.anteprima:
            self.scrivi(colore(f"  [anteprima] {descrizione}", "tenue"))
            return False
        self.registra(descrizione)
        return True

    def comando(self, comando: Sequence[str], validi: Sequence[int] = (0,)) -> Esito:
        """Esegue un comando mostrando l'output in tempo reale."""
        testo = subprocess.list2cmdline(comando)
        if not self.modifica(testo):
            return Esito(Stato.ANTEPRIMA)
        self.scrivi(colore(f"> {testo}", "tenue"))
        codifica = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        try:
            processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except OSError as errore:
            return Esito(Stato.ERRORE, str(errore))
        assert processo.stdout is not None
        while True:
            blocco = os.read(processo.stdout.fileno(), 4096)
            if not blocco:
                break
            # sfc scrive in UTF-16 quando l'output e' reindirizzato.
            sys.stdout.write(blocco.replace(b"\x00", b"").decode(codifica, "replace"))
            sys.stdout.flush()
        codice = processo.wait()
        self.registra(f"codice uscita {codice}: {testo}")
        if codice in validi:
            return Esito(Stato.OK)
        return Esito(Stato.AVVISO, f"codice di uscita {codice}")

    @staticmethod
    def leggi(comando: Sequence[str]) -> str:
        """Esegue un comando di sola lettura e ne restituisce il testo."""
        risultato = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        return risultato.stdout.decode(f"cp{ctypes.windll.kernel32.GetOEMCP()}", "replace")

    @staticmethod
    def powershell(script: str, timeout: int = 180) -> str:
        prefisso = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ErrorActionPreference='SilentlyContinue';"
        codificato = base64.b64encode((prefisso + script).encode("utf-16-le")).decode()
        risultato = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificato],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=timeout,
        )
        return risultato.stdout.decode("utf-8", "replace").strip()

    def powershell_json(self, script: str, timeout: int = 180) -> object:
        testo = self.powershell(script, timeout)
        return json.loads(testo) if testo else None


# ---------- Check-up ----------

SCRIPT_CHECKUP = r"""
$os = Get-CimInstance Win32_OperatingSystem
$bios = Get-CimInstance Win32_BIOS
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
$dal = (Get-Date).AddDays(-30)
function Conta($f) { @(Get-WinEvent -FilterHashtable $f).Count }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$mp = Get-MpComputerStatus
$dump = @(Get-ChildItem 'C:\Windows\LiveKernelReports','C:\Windows\Minidump' -Recurse -File -Filter *.dmp)
$nv = & nvidia-smi --query-gpu=driver_version,temperature.gpu,power.draw,utilization.gpu --format=csv,noheader 2>$null
$bl = Get-BitLockerVolume | Where-Object MountPoint -eq 'C:'
[ordered]@{
  admin = $admin
  sistema = [ordered]@{
    nome = $os.Caption; build = $os.BuildNumber
    cpu = (Get-CimInstance Win32_Processor).Name.Trim()
    schedaMadre = (Get-CimInstance Win32_BaseBoard).Product
    bios = $bios.SMBIOSBIOSVersion
    dataBios = $bios.ReleaseDate.ToString('yyyy-MM-dd')
    etaBiosGiorni = [int]((Get-Date) - $bios.ReleaseDate).TotalDays
    oreAccensione = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)
    vociAvvio = @(Get-CimInstance Win32_StartupCommand).Count
  }
  memoria = [ordered]@{
    liberaGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    totaleGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
  }
  processi = @(Get-Process | Group-Object ProcessName | ForEach-Object { [ordered]@{ nome = $_.Name; MB = [int](($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB) } } | Sort-Object { $_.MB } -Descending | Select-Object -First 6)
  dischi = @(Get-PhysicalDisk | ForEach-Object {
    $c = $_ | Get-StorageReliabilityCounter
    [ordered]@{ nome = $_.FriendlyName; tipo = "$($_.MediaType)"; salute = "$($_.HealthStatus)"; temperatura = $c.Temperature; usura = $c.Wear; oreAccensione = $c.PowerOnHours; erroriLettura = $c.ReadErrorsUncorrected }
  })
  volumi = @(Get-Volume | Where-Object { $_.DriveLetter -and $_.Size -gt 0 } | ForEach-Object {
    [ordered]@{ lettera = "$($_.DriveLetter)"; liberoGB = [math]::Round($_.SizeRemaining / 1GB, 1); totaleGB = [math]::Round($_.Size / 1GB, 1); salute = "$($_.HealthStatus)" }
  })
  gpu = [ordered]@{ nome = $gpu.Name; driver = $gpu.DriverVersion; stato = "$nv" }
  stabilita = [ordered]@{
    spegnimenti = Conta @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=41; StartTime=$dal}
    whea = Conta @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=$dal}
    disco = Conta @{LogName='System'; ProviderName='disk','stornvme'; Level=1,2,3; StartTime=$dal}
    dump = $dump.Count
    dumpGB = [math]::Round(($dump | Measure-Object Length -Sum).Sum / 1GB, 1)
  }
  sicurezza = [ordered]@{
    defender = $mp.RealTimeProtectionEnabled
    firmeGiorni = $mp.AntivirusSignatureAge
    firewallSpenti = @(Get-NetFirewallProfile | Where-Object { -not $_.Enabled }).Count -gt 0
    bitlocker = "$($bl.ProtectionStatus)"
  }
  riavvioInSospeso = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
  aggiornamenti = @(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 3 | ForEach-Object { "$($_.HotFixID) $(if ($_.InstalledOn) { $_.InstalledOn.ToString('yyyy-MM-dd') })" })
} | ConvertTo-Json -Depth 6 -Compress
"""

SCRIPT_RETE = r"""
function Ping($ip) { ,@(Test-Connection -ComputerName $ip -Count 10 | ForEach-Object { $_.ResponseTime }) }
$gw = (Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4DefaultGateway.NextHop
$dns = Measure-Command { $script:ok = Resolve-DnsName 'www.microsoft.com' -DnsOnly }
[ordered]@{
  schede = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { "$($_.Name) | $($_.InterfaceDescription) | $($_.LinkSpeed)" })
  router = if ($gw) { Ping $gw } else { @() }
  cloudflare = Ping '1.1.1.1'
  google = Ping '8.8.8.8'
  dnsMs = [int]$dns.TotalMilliseconds
  dnsOk = [bool]$script:ok
} | ConvertTo-Json -Depth 4 -Compress
"""


def righe_report(dati: dict) -> List[str]:
    sistema = dati.get("sistema") or {}
    memoria = dati.get("memoria") or {}
    stabilita = dati.get("stabilita") or {}
    sicurezza = dati.get("sicurezza") or {}
    gpu = dati.get("gpu") or {}
    righe = [
        "SISTEMA",
        f"  {sistema.get('nome')} build {sistema.get('build')}",
        f"  CPU: {sistema.get('cpu')}",
        f"  Scheda madre: {sistema.get('schedaMadre')} | BIOS {sistema.get('bios')} del {sistema.get('dataBios')}",
        f"  Acceso da {sistema.get('oreAccensione')} ore | voci di avvio: {sistema.get('vociAvvio')}",
        "MEMORIA",
        f"  RAM libera: {memoria.get('liberaGB')} / {memoria.get('totaleGB')} GB",
    ]
    righe += [f"  {p.get('nome'):<26}{p.get('MB'):>7} MB" for p in come_lista(dati.get("processi"))]
    righe.append("DISCHI")
    for disco in come_lista(dati.get("dischi")):
        righe.append(f"  {disco.get('nome')} | {disco.get('tipo')} | {disco.get('salute')}")
        if disco.get("usura") is not None:
            righe.append(f"    {disco.get('temperatura')} C | usura {disco.get('usura')}% | {disco.get('oreAccensione')} ore | errori lettura {disco.get('erroriLettura')}")
    righe += [f"  {v.get('lettera')}: libero {v.get('liberoGB')} / {v.get('totaleGB')} GB | {v.get('salute')}" for v in come_lista(dati.get("volumi"))]
    righe += [
        "SCHEDA VIDEO",
        f"  {gpu.get('nome')} | driver {gpu.get('driver')}",
        f"  driver, temperatura, consumo, carico: {gpu.get('stato') or 'non disponibile'}",
        "STABILITA (30 giorni)",
        f"  Spegnimenti non puliti: {stabilita.get('spegnimenti')} | WHEA: {stabilita.get('whea')} | errori disco: {stabilita.get('disco')}",
    ]
    if dati.get("admin"):
        righe.append(f"  Dump presenti: {stabilita.get('dump')} ({stabilita.get('dumpGB')} GB)")
    righe += [
        "SICUREZZA",
        f"  Defender in tempo reale: {sicurezza.get('defender')} | firme di {sicurezza.get('firmeGiorni')} giorni fa",
        f"  BitLocker C: {sicurezza.get('bitlocker') or 'non letto'}",
        "AGGIORNAMENTI",
        f"  Riavvio in sospeso: {dati.get('riavvioInSospeso')}",
    ]
    righe += [f"  {voce}" for voce in come_lista(dati.get("aggiornamenti"))]
    return righe


def righe_rete(dati: dict) -> Tuple[List[str], List[str]]:
    righe = [f"  {scheda}" for scheda in come_lista(dati.get("schede"))]
    problemi: List[str] = []
    for nome, chiave in (("Router", "router"), ("Cloudflare", "cloudflare"), ("Google", "google")):
        tempi = come_lista(dati.get(chiave))
        if chiave == "router" and not tempi:
            continue
        s = statistiche_ping(tempi, 10)
        righe.append(f"  {nome:<11} media {s['media']:>6} ms | max {s['massimo']:>5} ms | jitter {s['jitter']:>5} ms | persi {int(s['persi'])}/10")
        if s["persi"]:
            problemi.append(f"Pacchetti persi verso {nome}: {int(s['persi'])}/10.")
    righe.append(f"  DNS: {dati.get('dnsMs')} ms")
    if not dati.get("dnsOk"):
        problemi.append("Risoluzione DNS non riuscita.")
    return righe, problemi


def checkup(ctx: Contesto) -> Esito:
    ctx.scrivi("Raccolta dati, circa un minuto...")
    dati = ctx.powershell_json(SCRIPT_CHECKUP)
    rete = ctx.powershell_json(SCRIPT_RETE)
    if not isinstance(dati, dict) or not isinstance(rete, dict):
        return Esito(Stato.ERRORE, "dati del sistema non leggibili")
    righe = [f"Check-up del {datetime.now():%Y-%m-%d %H:%M}"]
    if not dati.get("admin"):
        righe.append("Attenzione: senza amministratore alcune verifiche sono incomplete.")
    righe += righe_report(dati)
    righe_connessione, problemi_rete = righe_rete(rete)
    righe += ["RETE"] + righe_connessione
    problemi = trova_problemi(dati) + problemi_rete
    righe.append("RIEPILOGO")
    righe += [f"  ! {p}" for p in problemi] or ["  Nessun problema rilevato."]
    nome = f"report-{datetime.now():%Y%m%d-%H%M%S}"
    (DATI / f"{nome}.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (DATI / f"{nome}.json").write_text(json.dumps({"sistema": dati, "rete": rete, "problemi": problemi}, indent=2, ensure_ascii=False), encoding="utf-8")
    for riga in righe:
        ctx.scrivi(colore(riga, "avviso") if riga.startswith("  !") else riga)
    ctx.scrivi(f"\nReport: {DATI / nome}.txt")
    if problemi:
        return Esito(Stato.AVVISO, f"{len(problemi)} problemi rilevati")
    return Esito(Stato.OK, "nessun problema")


def test_rete(ctx: Contesto) -> Esito:
    dati = ctx.powershell_json(SCRIPT_RETE)
    if not isinstance(dati, dict):
        return Esito(Stato.ERRORE, "test non riuscito")
    righe, problemi = righe_rete(dati)
    for riga in righe:
        ctx.scrivi(riga)
    return Esito(Stato.AVVISO, " ".join(problemi)) if problemi else Esito(Stato.OK)


def programmi_avvio(ctx: Contesto) -> Esito:
    voci = come_lista(ctx.powershell_json("@(Get-CimInstance Win32_StartupCommand | Select-Object -Unique Name | ForEach-Object Name | Sort-Object) | ConvertTo-Json -Compress"))
    for voce in voci:
        ctx.scrivi(f"  {voce}")
    return Esito(Stato.OK, f"{len(voci)} programmi")


# ---------- Sicurezza ----------

def punto_ripristino(ctx: Contesto) -> Esito:
    if not ctx.modifica("Crea punto di ripristino"):
        return Esito(Stato.ANTEPRIMA)
    ctx.powershell("Enable-ComputerRestore -Drive 'C:\\'; Checkpoint-Computer -Description 'Ottimizza PC' -RestorePointType MODIFY_SETTINGS", timeout=600)
    testo = ctx.powershell("(Get-ComputerRestorePoint | Select-Object -Last 1 | ForEach-Object { $_.ConvertToDateTime($_.CreationTime).ToString('s') })")
    try:
        creato = datetime.fromisoformat(testo)
    except ValueError:
        raise SequenzaFermata("nessun punto di ripristino disponibile") from None
    # Windows crea al massimo un punto ogni 24 ore: uno recente protegge comunque.
    if datetime.now() - creato > timedelta(hours=24):
        raise SequenzaFermata(f"ultimo punto di ripristino troppo vecchio ({testo})")
    return Esito(Stato.OK, f"punto del {creato:%d/%m %H:%M}")


# ---------- Pulizia ----------

def pulizia_file(ctx: Contesto) -> Esito:
    limite = time.time() - GIORNI_FILE_VECCHI * 86400
    totale = errori = 0
    for modello in CARTELLE_PULIZIA:
        radice = os.path.expandvars(modello)
        if "%" in radice or not os.path.isdir(radice):
            continue
        liberati = 0
        for percorso, peso in file_da_pulire(radice, limite):
            if ctx.anteprima:
                liberati += peso
                continue
            try:
                os.remove(percorso)
                liberati += peso
            except OSError:
                errori += 1
        ctx.scrivi(f"  {radice}: {dimensione(liberati)}")
        totale += liberati
    if ctx.modifica("Svuota cache Ottimizzazione recapito"):
        ctx.powershell("Delete-DeliveryOptimizationCache -Force", timeout=300)
    ctx.registra(f"Pulizia: {totale} byte, {errori} file in uso")
    nota = f"{dimensione(totale)}, {errori} file in uso lasciati"
    return Esito(Stato.ANTEPRIMA if ctx.anteprima else Stato.OK, nota)


def pulizia_componenti(ctx: Contesto) -> Esito:
    return ctx.comando(["DISM", "/Online", "/Cleanup-Image", "/StartComponentCleanup"])


def svuota_cestino(ctx: Contesto) -> Esito:
    if not ctx.modifica("Svuota il Cestino"):
        return Esito(Stato.ANTEPRIMA)
    ctx.powershell("Clear-RecycleBin -Force")
    return Esito(Stato.OK)


def elimina_dump(ctx: Contesto) -> Esito:
    trovati = [Path(r"C:\Windows\MEMORY.DMP")]
    for cartella in CARTELLE_DUMP:
        try:
            trovati += list(Path(cartella).rglob("*.dmp"))
        except OSError:
            pass
    presenti = [file for file in trovati if file.exists()]
    peso = sum(file.stat().st_size for file in presenti)
    if not ctx.modifica(f"Elimina {len(presenti)} dump ({dimensione(peso)})"):
        return Esito(Stato.ANTEPRIMA)
    for file in presenti:
        file.unlink(missing_ok=True)
    return Esito(Stato.OK, dimensione(peso))


# ---------- Riparazione ----------

def ripara_immagine(ctx: Contesto) -> Esito:
    return ctx.comando(["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"])


def ripara_file(ctx: Contesto) -> Esito:
    esito = ctx.comando(["sfc", "/scannow"])
    if esito.stato is Stato.AVVISO:
        esito.nota = "vedi C:\\Windows\\Logs\\CBS\\CBS.log"
    return esito


def verifica_disco(ctx: Contesto) -> Esito:
    return ctx.comando(["chkdsk", "C:", "/scan"])


def ripara_disco(ctx: Contesto) -> Esito:
    esito = ctx.comando(["fsutil", "dirty", "set", "C:"])
    if esito.stato is Stato.OK:
        ctx.riavvio_necessario = True
        esito.nota = "riparazione al prossimo riavvio"
    return esito


def trim(ctx: Contesto) -> Esito:
    return ctx.comando(["defrag", "C:", "/L", "/V"])


# ---------- Servizi ----------

def leggi_backup() -> Dict[str, dict]:
    if BACKUP_SERVIZI.exists():
        return json.loads(BACKUP_SERVIZI.read_text(encoding="utf-8"))
    return {}


def scrivi_backup(backup: Dict[str, dict]) -> None:
    temporaneo = BACKUP_SERVIZI.with_suffix(".tmp")
    temporaneo.write_text(json.dumps(backup, indent=2, ensure_ascii=False), encoding="utf-8")
    temporaneo.replace(BACKUP_SERVIZI)


def imposta_servizi(ctx: Contesto, nomi: Iterable[str], avvio: str) -> Tuple[int, int]:
    riusciti = falliti = 0
    backup = leggi_backup()
    for nome in nomi:
        if nome in SERVIZI_PROTETTI:
            raise ValueError(f"Servizio protetto: {nome}")
        configurazione = ctx.leggi(["sc", "qc", nome])
        modo = leggi_avvio_servizio(configurazione)
        if modo is None:
            ctx.scrivi(colore(f"  [assente]  {nome}", "tenue"))
            continue
        if modo == avvio:
            ctx.scrivi(colore(f"  [gia' ok]  {nome}", "tenue"))
            continue
        if not ctx.modifica(f"Servizio {nome}: {modo} -> {avvio}"):
            continue
        if nome not in backup:
            backup[nome] = {"avvio": modo, "attivo": servizio_attivo(ctx.leggi(["sc", "query", nome]))}
            scrivi_backup(backup)
        subprocess.run(["sc", "stop", nome], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        risultato = subprocess.run(["sc", "config", nome, "start=", avvio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        if risultato.returncode == 0:
            ctx.scrivi(colore(f"  [fatto]    {nome} -> {avvio}", "ok"))
            riusciti += 1
        else:
            ctx.scrivi(colore(f"  [errore]   {nome}", "errore"))
            ctx.registra(f"ERRORE servizio {nome}")
            falliti += 1
    return riusciti, falliti


def esito_servizi(ctx: Contesto, riusciti: int, falliti: int) -> Esito:
    if ctx.anteprima:
        return Esito(Stato.ANTEPRIMA)
    if falliti:
        return Esito(Stato.AVVISO, f"{riusciti} modificati, {falliti} non modificabili")
    return Esito(Stato.OK, f"{riusciti} modificati")


def servizi_sicuri(ctx: Contesto) -> Esito:
    r1, f1 = imposta_servizi(ctx, SERVIZI_SICURI, "disabled")
    r2, f2 = imposta_servizi(ctx, SERVIZI_MANUALI, "demand")
    return esito_servizi(ctx, r1 + r2, f1 + f2)


def servizi_xbox(ctx: Contesto) -> Esito:
    return esito_servizi(ctx, *imposta_servizi(ctx, SERVIZI_XBOX, "disabled"))


def servizi_stampa(ctx: Contesto) -> Esito:
    return esito_servizi(ctx, *imposta_servizi(ctx, SERVIZI_STAMPA, "disabled"))


def ripristina_servizi(ctx: Contesto) -> Esito:
    backup = leggi_backup()
    if not backup:
        return Esito(Stato.OK, "nessun servizio da ripristinare")
    falliti = 0
    for nome, stato in list(backup.items()):
        if not ctx.modifica(f"Servizio {nome} -> {stato['avvio']}"):
            continue
        risultato = subprocess.run(["sc", "config", nome, "start=", stato["avvio"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        if risultato.returncode != 0:
            ctx.scrivi(colore(f"  [errore]   {nome}", "errore"))
            falliti += 1
            continue
        if stato.get("attivo"):
            subprocess.run(["sc", "start", nome], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        ctx.scrivi(colore(f"  [fatto]    {nome} -> {stato['avvio']}", "ok"))
        del backup[nome]
        scrivi_backup(backup)
    if ctx.anteprima:
        return Esito(Stato.ANTEPRIMA)
    return Esito(Stato.AVVISO, f"{falliti} non ripristinati") if falliti else Esito(Stato.OK, "tutti ripristinati")


def stato_servizi(ctx: Contesto) -> Esito:
    for nome in SERVIZI_SICURI + SERVIZI_MANUALI + SERVIZI_XBOX + SERVIZI_STAMPA:
        modo = leggi_avvio_servizio(ctx.leggi(["sc", "qc", nome])) or "assente"
        attivo = "attivo" if servizio_attivo(ctx.leggi(["sc", "query", nome])) else "fermo"
        ctx.scrivi(f"  {nome:<32}{modo:<14}{attivo}")
    return Esito(Stato.OK, f"{len(leggi_backup())} nel backup")


# ---------- Rete ----------

def comandi_in_serie(ctx: Contesto, comandi: Iterable[Sequence[str]]) -> Esito:
    esiti = [ctx.comando(comando) for comando in comandi]
    if ctx.anteprima:
        return Esito(Stato.ANTEPRIMA)
    falliti = sum(esito.stato is not Stato.OK for esito in esiti)
    return Esito(Stato.AVVISO, f"{falliti} comandi non riusciti") if falliti else Esito(Stato.OK)


def ottimizza_rete(ctx: Contesto) -> Esito:
    return comandi_in_serie(ctx, (
        ["ipconfig", "/flushdns"],
        ["netsh", "interface", "ip", "delete", "arpcache"],
        ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"],
        ["netsh", "int", "tcp", "set", "global", "rss=enabled"],
    ))


def ripara_rete(ctx: Contesto) -> Esito:
    esito = comandi_in_serie(ctx, (
        ["netsh", "winsock", "reset"],
        ["netsh", "int", "ip", "reset"],
        ["ipconfig", "/flushdns"],
    ))
    ctx.riavvio_necessario = ctx.riavvio_necessario or not ctx.anteprima
    return esito


def imposta_dns(ctx: Contesto, server: Optional[Sequence[str]]) -> Esito:
    descrizione = ", ".join(server) if server else "automatico"
    if not ctx.modifica(f"DNS delle schede attive: {descrizione}"):
        return Esito(Stato.ANTEPRIMA)
    azione = f"-ServerAddresses {','.join(repr(s) for s in server)}" if server else "-ResetServerAddresses"
    ctx.powershell(f"Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {{ Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex {azione} }}; Clear-DnsClientCache")
    return Esito(Stato.OK, descrizione)


# ---------- Ottimizzazioni ----------

REGISTRO_PRIMA_DI_SCRIVERE = None  # funzione (radice, chiave, valore) chiamata prima di ogni scrittura


def scrivi_registro(ctx: Contesto, radice: str, chiave: str, valore: str, dato: int) -> None:
    if not ctx.modifica(f"Registro {radice}\\{chiave}\\{valore} = {dato}"):
        return
    import winreg
    if REGISTRO_PRIMA_DI_SCRIVERE is not None:  # la console annota il valore precedente per l'annullamento
        REGISTRO_PRIMA_DI_SCRIVERE(radice, chiave, valore)
    with winreg.CreateKeyEx(getattr(winreg, radice), chiave, 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, valore, 0, winreg.REG_DWORD, dato)


def imposta_avvio_rapido(ctx: Contesto, attivo: bool) -> Esito:
    scrivi_registro(ctx, "HKEY_LOCAL_MACHINE", CHIAVE_AVVIO_RAPIDO, "HiberbootEnabled", int(attivo))
    return Esito(Stato.ANTEPRIMA if ctx.anteprima else Stato.OK)


def imposta_game_dvr(ctx: Contesto, attivo: bool) -> Esito:
    scrivi_registro(ctx, "HKEY_CURRENT_USER", CHIAVE_GAME_CONFIG, "GameDVR_Enabled", int(attivo))
    scrivi_registro(ctx, "HKEY_CURRENT_USER", CHIAVE_GAME_DVR, "AppCaptureEnabled", int(attivo))
    return Esito(Stato.ANTEPRIMA if ctx.anteprima else Stato.OK)


# ---------- Catalogo ----------

@dataclass(frozen=True)
class Passo:
    id: int
    gruppo: str
    titolo: str
    azione: Callable[[Contesto], Esito]
    minuti: float = 0.5
    modifica: bool = True
    conferma: str = ""


PASSI: Tuple[Passo, ...] = (
    Passo(1, "Sicurezza e controllo", "Punto di ripristino", punto_ripristino, 2),
    Passo(2, "Sicurezza e controllo", "Check-up completo con report", checkup, 2, modifica=False),
    Passo(3, "Sicurezza e controllo", "Test connessione", test_rete, 1, modifica=False),
    Passo(4, "Sicurezza e controllo", "Stato dei servizi gestiti", stato_servizi, 0.5, modifica=False),
    Passo(5, "Sicurezza e controllo", "Programmi all'avvio", programmi_avvio, 0.5, modifica=False),
    Passo(6, "Pulizia", "Temporanei e cache", pulizia_file, 3),
    Passo(7, "Pulizia", "Componenti Windows obsoleti", pulizia_componenti, 10),
    Passo(8, "Pulizia", "Svuota il Cestino", svuota_cestino, 0.5, conferma="Il contenuto del Cestino viene eliminato per sempre."),
    Passo(9, "Pulizia", "Elimina i dump dei crash", elimina_dump, 0.5, conferma="I dump servono per analizzare il problema della GPU."),
    Passo(10, "Riparazione", "Ripara immagine Windows (DISM)", ripara_immagine, 15),
    Passo(11, "Riparazione", "Ripara file di sistema (SFC)", ripara_file, 15),
    Passo(12, "Riparazione", "Verifica disco C: senza riavvio", verifica_disco, 5),
    Passo(13, "Riparazione", "Riparazione disco C: al riavvio", ripara_disco, 0.5, conferma="Il prossimo avvio sara' piu' lungo."),
    Passo(14, "Riparazione", "TRIM dell'SSD", trim, 2),
    Passo(15, "Servizi", "Disattiva servizi inutili sicuri", servizi_sicuri, 1),
    Passo(16, "Servizi", "Disattiva Xbox e Game Pass", servizi_xbox, 1, conferma="Game Pass e i giochi dello Store smettono di funzionare."),
    Passo(17, "Servizi", "Disattiva stampa e scanner", servizi_stampa, 0.5, conferma="Si blocca anche Stampa su PDF."),
    Passo(18, "Servizi", "RIPRISTINA i servizi modificati", ripristina_servizi, 1),
    Passo(19, "Rete", "Ottimizza connessione (TCP e cache DNS)", ottimizza_rete, 0.5),
    Passo(20, "Rete", "DNS Cloudflare", lambda ctx: imposta_dns(ctx, ("1.1.1.1", "1.0.0.1")), 0.5),
    Passo(21, "Rete", "DNS Google", lambda ctx: imposta_dns(ctx, ("8.8.8.8", "8.8.4.4")), 0.5),
    Passo(22, "Rete", "DNS automatico", lambda ctx: imposta_dns(ctx, None), 0.5),
    Passo(23, "Rete", "Riparazione rete completa", ripara_rete, 0.5, conferma="Un IP statico andrebbe perso. Serve un riavvio."),
    Passo(24, "Sistema", "Disattiva Avvio rapido", lambda ctx: imposta_avvio_rapido(ctx, False), 0.5),
    Passo(25, "Sistema", "Riattiva Avvio rapido", lambda ctx: imposta_avvio_rapido(ctx, True), 0.5),
    Passo(26, "Sistema", "Disattiva registrazione giochi", lambda ctx: imposta_game_dvr(ctx, False), 0.5),
    Passo(27, "Sistema", "Riattiva registrazione giochi", lambda ctx: imposta_game_dvr(ctx, True), 0.5),
)
PER_ID = {passo.id: passo for passo in PASSI}

SEQUENZE: Dict[str, Tuple[str, Tuple[int, ...]]] = {
    "rapida": ("Rapida: spazio e connessione", (1, 2, 6, 14, 19)),
    "riparazione": ("Riparazione: Windows e disco", (1, 2, 10, 11, 12, 14)),
    "completa": ("Completa: tutto il necessario", (1, 2, 6, 7, 10, 11, 12, 14, 15, 19, 24, 2)),
}
LETTERE_SEQUENZE = {"r": "rapida", "p": "riparazione", "c": "completa"}
ALTERNATIVE = ({20, 21, 22}, {24, 25}, {26, 27})


def prepara_sequenza(ids: Sequence[int]) -> Tuple[List[int], List[str]]:
    """Mette la sicurezza prima di tutto e segnala i passaggi in conflitto."""
    sequenza = list(ids)
    avvisi: List[str] = []
    modifiche = [i for i in sequenza if PER_ID[i].modifica and i != 1]
    if modifiche:
        if 1 in sequenza:
            sequenza.remove(1)
        sequenza.insert(0, 1)
    if 11 in sequenza and 10 in sequenza and sequenza.index(11) < sequenza.index(10):
        avvisi.append("Conviene eseguire DISM (10) prima di SFC (11).")
    for gruppo in ALTERNATIVE:
        scelti = [i for i in sequenza if i in gruppo]
        if len(scelti) > 1:
            avvisi.append(f"I passaggi {scelti} si annullano: vale l'ultimo.")
    return sequenza, avvisi


# ---------- Esecuzione ----------

def spazio_libero() -> int:
    return shutil.disk_usage("C:\\").free


def esegui_passo(ctx: Contesto, passo: Passo) -> Esito:
    try:
        return passo.azione(ctx)
    except SequenzaFermata:
        raise
    except subprocess.TimeoutExpired:
        return Esito(Stato.ERRORE, "tempo scaduto")
    except Exception as errore:  # un passaggio non deve fermare gli altri
        ctx.registra(f"ERRORE {passo.titolo}: {errore!r}")
        return Esito(Stato.ERRORE, str(errore))


def esegui_sequenza(ctx: Contesto, ids: Sequence[int]) -> List[Tuple[Passo, Esito, float]]:
    risultati: List[Tuple[Passo, Esito, float]] = []
    inizio_spazio = spazio_libero()
    inizio = time.monotonic()
    fermata = ""
    for numero, identificativo in enumerate(ids, 1):
        passo = PER_ID[identificativo]
        if fermata:
            risultati.append((passo, Esito(Stato.SALTATO, "sequenza fermata"), 0.0))
            continue
        ctx.scrivi("\n" + colore(f"[{numero}/{len(ids)}] {passo.titolo}", "titolo"))
        partenza = time.monotonic()
        try:
            esito = esegui_passo(ctx, passo)
        except SequenzaFermata as motivo:
            fermata = str(motivo)
            esito = Esito(Stato.ERRORE, fermata)
        except KeyboardInterrupt:
            esito = Esito(Stato.SALTATO, "interrotto da te")
            if not chiedi("\nContinuare con il passaggio successivo?"):
                fermata = "interrotta da te"
        risultati.append((passo, esito, time.monotonic() - partenza))
    mostra_riepilogo(ctx, risultati, spazio_libero() - inizio_spazio, time.monotonic() - inizio, fermata)
    return risultati


def mostra_riepilogo(ctx: Contesto, risultati: Sequence[Tuple[Passo, Esito, float]], guadagno: int, tempo: float, fermata: str) -> None:
    tipi = {Stato.OK: "ok", Stato.AVVISO: "avviso", Stato.ERRORE: "errore", Stato.SALTATO: "tenue", Stato.ANTEPRIMA: "tenue"}
    ctx.scrivi("\n" + colore("RIEPILOGO", "titolo"))
    for passo, esito, secondi in risultati:
        etichetta = colore(f"{esito.stato.value:<10}", tipi[esito.stato])
        ctx.scrivi(f"  {etichetta}{passo.titolo:<42}{durata(secondi):>8}  {esito.nota}")
        ctx.registra(f"{esito.stato.value} {passo.titolo} {esito.nota}")
    variazione = "" if ctx.anteprima else f" | Spazio liberato: {dimensione(max(guadagno, 0))}"
    ctx.scrivi(f"\nDurata: {durata(tempo)}{variazione} | Libero ora: {dimensione(spazio_libero())}")
    if fermata:
        ctx.scrivi(colore(f"Sequenza fermata: {fermata}", "errore"))
    if ctx.riavvio_necessario:
        ctx.scrivi(colore("Riavvia il PC per completare le modifiche.", "avviso"))


def chiedi(domanda: str) -> bool:
    return input(f"{domanda} [s/N] ").strip().lower() in ("s", "si", "y")


def mostra_catalogo() -> None:
    gruppo = ""
    for passo in PASSI:
        if passo.gruppo != gruppo:
            gruppo = passo.gruppo
            print("\n" + colore(gruppo, "titolo"))
        print(f"  {passo.id:>2}  {passo.titolo}")
    print("\n" + colore("Sequenze pronte", "titolo"))
    for lettera, chiave in LETTERE_SEQUENZE.items():
        descrizione, ids = SEQUENZE[chiave]
        print(f"  {lettera.upper()}   {descrizione} ({' '.join(map(str, ids))})")


def conferma_piano(ids: Sequence[int], avvisi: Sequence[str], automatico: bool, anteprima: bool) -> bool:
    print("\n" + colore("Sequenza da eseguire", "titolo"))
    for numero, identificativo in enumerate(ids, 1):
        print(f"  {numero:>2}. {PER_ID[identificativo].titolo}")
    print(f"\nDurata stimata: circa {max(1, round(sum(PER_ID[i].minuti for i in ids)))} minuti")
    for avviso in avvisi:
        print(colore(f"Nota: {avviso}", "avviso"))
    if automatico or anteprima:
        return True
    # Tutte le domande vengono fatte ora, cosi' la sequenza procede da sola.
    for identificativo in ids:
        passo = PER_ID[identificativo]
        if passo.conferma and not chiedi(f"{passo.titolo}: {passo.conferma} Confermi?"):
            return False
    return chiedi("Avviare la sequenza?")


def menu(ctx: Contesto) -> None:
    while True:
        os.system("cls")  # testo fisso, nessun input utente
        print(colore("OTTIMIZZA PC", "titolo") + (colore("  ANTEPRIMA: nessuna modifica", "avviso") if ctx.anteprima else ""))
        mostra_catalogo()
        print(f"\nLibero su C: {dimensione(spazio_libero())}")
        print("Scrivi i numeri nell'ordine voluto (es. 2 6 10-12) oppure una lettera. Q per uscire.")
        scelta = input("> ").strip()
        if scelta.lower() == "q":
            return
        chiave = LETTERE_SEQUENZE.get(scelta.lower())
        try:
            ids = list(SEQUENZE[chiave][1]) if chiave else leggi_selezione(scelta, list(PER_ID))
        except ValueError as errore:
            input(colore(f"{errore} Premi Invio.", "errore"))
            continue
        ids, avvisi = prepara_sequenza(ids)
        if conferma_piano(ids, avvisi, False, ctx.anteprima):
            esegui_sequenza(ctx, ids)
            input("\nPremi Invio per tornare al menu.")


def e_amministratore() -> bool:
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def riavvia_come_amministratore() -> None:
    parametri = subprocess.list2cmdline([str(Path(__file__).resolve()), *sys.argv[1:], "--pausa"])
    codice = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, parametri, str(CARTELLA), 1)
    if codice <= 32:
        sys.exit("Servono i permessi di amministratore.")


def crea_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manutenzione di Windows con passaggi in sequenza.")
    parser.add_argument("--anteprima", action="store_true", help="mostra le azioni senza modificare nulla")
    parser.add_argument("--elenco", action="store_true", help="elenca passaggi e sequenze")
    parser.add_argument("--esegui", nargs="+", metavar="N", help="passaggi da eseguire nell'ordine dato")
    parser.add_argument("--sequenza", choices=sorted(SEQUENZE), help="sequenza pronta")
    parser.add_argument("--si", action="store_true", help="salta le domande di conferma")
    parser.add_argument("--pausa", action="store_true", help=argparse.SUPPRESS)
    return parser


def esegui_da_riga_di_comando(ctx: Contesto, opzioni: argparse.Namespace) -> int:
    try:
        ids = list(SEQUENZE[opzioni.sequenza][1]) if opzioni.sequenza else leggi_selezione(" ".join(opzioni.esegui), list(PER_ID))
    except ValueError as errore:
        print(errore)
        return 2
    ids, avvisi = prepara_sequenza(ids)
    if not conferma_piano(ids, avvisi, opzioni.si, ctx.anteprima):
        return 1
    risultati = esegui_sequenza(ctx, ids)
    if opzioni.pausa:
        input("\nPremi Invio per chiudere.")
    return 1 if any(esito.stato is Stato.ERRORE for _, esito, _ in risultati) else 0


def main(argomenti: Optional[Sequence[str]] = None) -> int:
    opzioni = crea_parser().parse_args(argomenti)
    os.system("")  # abilita i colori ANSI nella console di Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if opzioni.elenco:
        mostra_catalogo()
        return 0
    if not opzioni.anteprima and not e_amministratore():
        riavvia_come_amministratore()
        return 0
    ctx = Contesto(opzioni.anteprima)
    if opzioni.esegui or opzioni.sequenza:
        return esegui_da_riga_di_comando(ctx, opzioni)
    try:
        menu(ctx)
    except (KeyboardInterrupt, EOFError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
