"""Live performance monitor based on Windows performance counters (PDH), stdlib only.

A sampler thread starts on the first request and stops after a while without readers,
so the agent costs nothing when nobody watches the Performance page."""
from __future__ import annotations

import ctypes
import os
import re
import threading
import time
from collections import deque
from ctypes import wintypes
from typing import Callable, Deque, Dict, List, Optional

PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2
MB = 1024 ** 2
_INSTANCE = re.compile(r"#\d+$")


class _FmtValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _FmtItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _FmtValue)]


def top_processes(cpu: Dict[str, float], memory: Dict[str, float], cpus: int, n: int = 8) -> Dict[str, List[dict]]:
    """Aggregates process instances (chrome, chrome#1...) and ranks them."""
    def somma(valori: Dict[str, float]) -> Dict[str, float]:
        totali: Dict[str, float] = {}
        for nome, valore in valori.items():
            if nome in ("_Total", "Idle"):
                continue
            base = _INSTANCE.sub("", nome)
            totali[base] = totali.get(base, 0.0) + max(0.0, valore)
        return totali

    per_cpu = somma(cpu)
    per_memoria = somma(memory)
    return {
        "cpu": [{"name": k, "cpu": round(v / max(1, cpus), 1)} for k, v in sorted(per_cpu.items(), key=lambda x: -x[1])[:n]],
        "memory": [{"name": k, "mb": int(round(v / MB))} for k, v in sorted(per_memoria.items(), key=lambda x: -x[1])[:n]],
    }


class _Pdh:
    def __init__(self):
        self.dll = ctypes.WinDLL("pdh.dll")
        self.query = wintypes.HANDLE()
        self._check(self.dll.PdhOpenQueryW(None, None, ctypes.byref(self.query)))

    @staticmethod
    def _check(codice: int) -> None:
        if codice != 0:
            raise OSError(f"PDH error 0x{codice & 0xFFFFFFFF:08X}")

    def add(self, path: str) -> wintypes.HANDLE:
        contatore = wintypes.HANDLE()
        self._check(self.dll.PdhAddEnglishCounterW(self.query, path, None, ctypes.byref(contatore)))
        return contatore

    def collect(self) -> None:
        self._check(self.dll.PdhCollectQueryData(self.query))

    def value(self, contatore) -> Optional[float]:
        valore = _FmtValue()
        codice = self.dll.PdhGetFormattedCounterValue(contatore, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, None, ctypes.byref(valore))
        return valore.doubleValue if codice == 0 and valore.CStatus in (0, 1) else None

    def array(self, contatore) -> Dict[str, float]:
        dimensione, numero = wintypes.DWORD(0), wintypes.DWORD(0)
        codice = self.dll.PdhGetFormattedCounterArrayW(contatore, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, ctypes.byref(dimensione), ctypes.byref(numero), None)
        if codice & 0xFFFFFFFF != PDH_MORE_DATA:
            return {}
        buffer = (ctypes.c_byte * dimensione.value)()
        codice = self.dll.PdhGetFormattedCounterArrayW(contatore, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, ctypes.byref(dimensione), ctypes.byref(numero), buffer)
        if codice != 0:
            return {}
        voci = ctypes.cast(buffer, ctypes.POINTER(_FmtItem))
        risultato: Dict[str, float] = {}
        for i in range(numero.value):
            voce = voci[i]
            if voce.FmtValue.CStatus in (0, 1):
                nome, copia = voce.szName, 0
                # Duplicate instance names come back as separate items: keep them apart (name#n).
                while nome in risultato:
                    copia += 1
                    nome = f"{voce.szName}#{copia}"
                risultato[nome] = voce.FmtValue.doubleValue
        return risultato


class SystemReader:
    """Reads one sample: CPU, memory, disk and network, plus the busiest processes."""

    def __init__(self):
        from .inventory import memory_status
        self._memory = memory_status
        self.cpus = os.cpu_count() or 1
        self.pdh = _Pdh()
        try:
            self.cpu = self.pdh.add(r"\Processor Information(_Total)\% Processor Utility")
        except OSError:
            self.cpu = self.pdh.add(r"\Processor(_Total)\% Processor Time")
        self.disk_read = self.pdh.add(r"\PhysicalDisk(_Total)\Disk Read Bytes/sec")
        self.disk_write = self.pdh.add(r"\PhysicalDisk(_Total)\Disk Write Bytes/sec")
        self.disk_idle = self.pdh.add(r"\PhysicalDisk(_Total)\% Idle Time")
        self.net_in = self.pdh.add(r"\Network Interface(*)\Bytes Received/sec")
        self.net_out = self.pdh.add(r"\Network Interface(*)\Bytes Sent/sec")
        self.proc_cpu = self.pdh.add(r"\Process(*)\% Processor Time")
        self.proc_mem = self.pdh.add(r"\Process(*)\Working Set - Private")
        self.pdh.collect()  # rate counters need two collections
        time.sleep(0.25)

    def __call__(self) -> dict:
        self.pdh.collect()
        memoria = self._memory()
        inattivo = self.pdh.value(self.disk_idle)
        return {
            "cpu": round(min(100.0, self.pdh.value(self.cpu) or 0.0), 1),
            "memory_pct": memoria["load_pct"],
            "memory_used_gb": round(memoria["total_gb"] - memoria["free_gb"], 1),
            "memory_total_gb": memoria["total_gb"],
            "commit_pct": memoria["commit_pct"],
            "disk_read": int(self.pdh.value(self.disk_read) or 0),
            "disk_write": int(self.pdh.value(self.disk_write) or 0),
            "disk_busy": round(max(0.0, min(100.0, 100.0 - inattivo)), 1) if inattivo is not None else None,
            "net_in": int(sum(self.pdh.array(self.net_in).values())),
            "net_out": int(sum(self.pdh.array(self.net_out).values())),
            "processes": top_processes(self.pdh.array(self.proc_cpu), self.pdh.array(self.proc_mem), self.cpus),
        }


class LiveMonitor:
    def __init__(self, reader: Optional[Callable[[], dict]] = None, interval: float = 2.0, history: int = 150,
                 idle_stop: float = 120.0, clock: Callable[[], float] = time.time):
        self._factory = reader
        self._reader: Optional[Callable[[], dict]] = reader
        self.interval = interval
        self.idle_stop = idle_stop
        self.clock = clock
        self._samples: Deque[dict] = deque(maxlen=history)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._last_request = 0.0
        self.last_error = ""

    def sample_once(self) -> None:
        try:
            if self._reader is None:
                self._reader = SystemReader()
            lettura = self._reader()
        except Exception as errore:  # counters can be disabled or corrupted on some PCs
            self.last_error = str(errore)
            return
        with self._lock:
            self._samples.append(dict(lettura, t=self.clock()))

    def samples(self, since: float) -> List[dict]:
        with self._lock:
            return [s for s in self._samples if s["t"] > since]

    def request(self, since: float) -> List[dict]:
        """Called by the API: keeps the sampler alive and returns new samples."""
        self._last_request = time.monotonic()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="wmm-live", daemon=True)
            self._thread.start()
            if not self._samples:
                time.sleep(min(1.0, self.interval))
        return self.samples(since)

    def _run(self) -> None:
        while time.monotonic() - self._last_request < self.idle_stop:
            self.sample_once()
            time.sleep(self.interval)
