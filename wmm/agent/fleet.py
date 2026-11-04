"""The PCs of the network, read-only. A PC can share a short summary (health, problems, unsafe programs, free space)
on a second port, protected by a key; a console lists other PCs and gathers their summaries. Nothing can be changed
through it, the key is kept only as a hash on the sharing PC, and the console contacts only private (LAN) addresses."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, List, Optional

from . import notify

DEFAULT_PORT = 8766
SUMMARY_PATH = "/fleet/v1/summary"
KEY_HEADER = "X-WMM-Fleet-Key"
TIMEOUT = 4
MAX_PCS = 200
FIREWALL_RULE = "Windows Maintenance Manager - PC summary"


class FleetError(ValueError):
    """Invalid settings or a PC that cannot be reached."""


def key_hash(chiave: str) -> str:
    return hashlib.sha256(chiave.encode("utf-8")).hexdigest()


def lan_address(indirizzo: str) -> str:
    """The IP to contact for `indirizzo` (a name or an IP), only when it is on the local network."""
    testo = (indirizzo or "").strip()
    if not testo or len(testo) > 253 or any(c in testo for c in "/\\@?#: "):
        raise FleetError("Write a PC name or an IP address, without http:// or a port.")
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(testo))
    except (OSError, ValueError):
        raise FleetError(f"{testo} cannot be found on the network.") from None
    if not (ip.is_private or ip.is_loopback or ip.is_link_local) or ip.is_multicast or ip.is_unspecified:
        raise FleetError(f"{testo} ({ip}) is not on the local network: only LAN addresses are contacted.")
    return str(ip)


class Fleet:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            dati = json.loads(self.path.read_text(encoding="utf-8"))
            return dati if isinstance(dati, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, dati: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dati, indent=1), encoding="utf-8")

    # ---------- sharing this PC ----------

    def share(self) -> dict:
        dati = self._read()
        return {"enabled": bool(dati.get("share")), "port": int(dati.get("port") or DEFAULT_PORT), "has_key": bool(dati.get("key_hash"))}

    def set_share(self, attivo, porta) -> dict:
        if not isinstance(attivo, bool):
            raise FleetError("'enabled' must be true or false.")
        try:
            porta = int(porta or DEFAULT_PORT)
        except (TypeError, ValueError):
            raise FleetError("The port must be a number.") from None
        if not 1024 <= porta <= 65535:
            raise FleetError("Choose a port between 1024 and 65535.")
        with self._lock:
            dati = self._read()
            if attivo and not dati.get("key_hash"):
                raise FleetError("Create a key first: other PCs need it to read the summary.")
            dati.update(share=attivo, port=porta)
            self._write(dati)
        return self.share()

    def new_key(self) -> str:
        """A new sharing key, returned once: only its hash is kept here."""
        chiave = secrets.token_urlsafe(24)
        with self._lock:
            dati = self._read()
            dati["key_hash"] = key_hash(chiave)
            self._write(dati)
        return chiave

    def accepts(self, chiave: str) -> bool:
        atteso = self._read().get("key_hash") or ""
        return bool(atteso and chiave) and hmac.compare_digest(atteso, key_hash(chiave))

    # ---------- the PCs this console reads ----------

    def pcs(self) -> List[dict]:
        return [{k: p.get(k) for k in ("id", "name", "address", "port")} for p in self._read().get("pcs", [])]

    def add(self, nome, indirizzo, porta, chiave) -> dict:
        if not isinstance(nome, str) or not nome.strip() or len(nome) > 60:
            raise FleetError("Give the PC a name (60 characters at most).")
        if not isinstance(chiave, str) or not 16 <= len(chiave) <= 100:
            raise FleetError("Paste the key shown on the other PC when sharing was turned on.")
        if not isinstance(indirizzo, str):
            raise FleetError("Write a PC name or an IP address.")
        lan_address(indirizzo)
        try:
            porta = int(porta or DEFAULT_PORT)
        except (TypeError, ValueError):
            raise FleetError("The port must be a number.") from None
        if not 1 <= porta <= 65535:
            raise FleetError("Invalid port.")
        with self._lock:
            dati = self._read()
            elenco = dati.setdefault("pcs", [])
            if len(elenco) >= MAX_PCS:
                raise FleetError(f"At most {MAX_PCS} PCs.")
            voce = {"id": secrets.token_hex(6), "name": nome.strip(), "address": indirizzo.strip(), "port": porta, "key": notify.protect(chiave)}
            elenco.append(voce)
            self._write(dati)
        return {k: voce[k] for k in ("id", "name", "address", "port")}

    def remove(self, pc_id: str) -> bool:
        with self._lock:
            dati = self._read()
            prima = len(dati.get("pcs", []))
            dati["pcs"] = [p for p in dati.get("pcs", []) if p.get("id") != pc_id]
            self._write(dati)
            return len(dati["pcs"]) < prima

    def gather(self, fetch: Optional[Callable[[str, int, str], dict]] = None) -> List[dict]:
        """The summary of every PC, read in parallel; an unreachable PC is a row with its error, never a failure."""
        fetch = fetch or fetch_summary
        voci = self._read().get("pcs", [])

        def una(p: dict) -> dict:
            riga = {"id": p.get("id"), "name": p.get("name"), "address": p.get("address"), "port": p.get("port")}
            try:
                riga.update(summary=fetch(p["address"], int(p["port"]), notify.unprotect(p.get("key", ""))), status="online")
            except Exception as errore:  # noqa: BLE001 - every failure becomes the row's message
                riga.update(status="offline", error=str(errore)[:200])
            return riga
        if not voci:
            return []
        with ThreadPoolExecutor(max_workers=min(16, len(voci)), thread_name_prefix="wmm-fleet") as pool:
            return list(pool.map(una, voci))


def fetch_summary(indirizzo: str, porta: int, chiave: str) -> dict:
    ip = lan_address(indirizzo)
    if not chiave:
        raise FleetError("the key could not be read: remove the PC and add it again")
    richiesta = urllib.request.Request(f"http://{ip}:{int(porta)}{SUMMARY_PATH}", headers={KEY_HEADER: chiave})
    try:
        with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
            dati = json.loads(risposta.read(64 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as errore:
        raise FleetError("wrong key" if errore.code == 403 else f"HTTP {errore.code}") from None
    except (OSError, ValueError) as errore:
        raise FleetError(f"not reachable ({getattr(errore, 'reason', errore)})") from None
    if not isinstance(dati, dict):
        raise FleetError("not a summary")
    return clean_summary(dati)


def clean_summary(dati: dict) -> dict:
    """Another PC is not trusted: only the expected fields, with their types and sizes, reach the page."""
    def numero(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and -1e12 < v < 1e12 else None

    def testo(v, massimo=80):
        return v[:massimo] if isinstance(v, str) else None
    punteggi = dati.get("scores") if isinstance(dati.get("scores"), dict) else {}
    insicuri = dati.get("unsafe_apps")
    return {
        "hostname": testo(dati.get("hostname"), 64), "machine_id": testo(dati.get("machine_id"), 80), "version": testo(dati.get("version"), 20),
        "overall": numero(dati.get("overall")), "open_issues": numero(dati.get("open_issues")),
        "scores": {str(k)[:20]: numero(v) for k, v in list(punteggi.items())[:20]},
        "unsafe_apps": [x[:120] for x in insicuri[:50] if isinstance(x, str)] if isinstance(insicuri, list) else None,
        "c_free_gb": numero(dati.get("c_free_gb")), "c_total_gb": numero(dati.get("c_total_gb")),
        "last_scan": testo(dati.get("last_scan"), 32), "uptime_seconds": numero(dati.get("uptime_seconds")),
    }


# ---------- the sharing server ----------

def summary_server(fleet: Fleet, porta: int, riassunto: Callable[[], dict]) -> ThreadingHTTPServer:
    """A server on every interface that answers one read-only question with the right key, and 404 to anything else."""

    class Riassunto(BaseHTTPRequestHandler):
        server_version = "WMM-Fleet"

        def log_message(self, *argomenti):  # quiet: the console log is for the agent
            pass

        def _answer(self, stato: int, corpo: dict) -> None:
            dati = json.dumps(corpo).encode("utf-8")
            self.send_response(stato)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dati)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dati)

        def do_GET(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
            if self.path != SUMMARY_PATH:
                self._answer(404, {"error": "Not found."})
            elif not fleet.accepts(self.headers.get(KEY_HEADER, "")):
                self._answer(403, {"error": "Wrong key."})
            else:
                self._answer(200, riassunto())

        def do_POST(self):  # noqa: N802
            self._answer(405, {"error": "Read-only."})

        do_PUT = do_DELETE = do_PATCH = do_POST

    server = ThreadingHTTPServer(("0.0.0.0", porta), Riassunto)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="wmm-fleet-share", daemon=True).start()
    return server


def firewall_rule(porta: int) -> dict:
    """Lets PCs of the local subnet (only) reach the summary port."""
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE}"], capture_output=True)
    risultato = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={FIREWALL_RULE}", "dir=in", "action=allow",
                                "protocol=TCP", f"localport={int(porta)}", "remoteip=localsubnet", "profile=private,domain"],
                               capture_output=True, text=True)
    if risultato.returncode != 0:
        raise OSError((risultato.stdout or risultato.stderr).strip()[-300:] or "netsh refused the rule")
    return {"rule": FIREWALL_RULE, "port": int(porta)}


def for_data_dir(data_dir: Path) -> Fleet:
    return Fleet(Path(data_dir) / "fleet.json")
