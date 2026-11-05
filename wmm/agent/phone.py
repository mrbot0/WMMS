"""The console from a phone (2.8). A small page on its own port, reachable only from the local network, that shows the
summary of this PC, its open problems, and runs reports and safe fixes (never moderate or high-risk ones, never your
own tools). Pairing: the console shows a one-time code of 16 characters for 10 minutes; the phone types it once and
keeps it. The code is the secret: it never travels on the network, every request is signed with it (HMAC-SHA256 with a
timestamp and a nonce, refused when older than two minutes or replayed), exactly like the requests between PCs.
A paired phone can be removed from the console at any time."""
from __future__ import annotations

import hmac
import ipaddress
import json
import re
import secrets
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, List, Optional

from . import notify
from .fleet import MAX_SKEW, allowed, clean_run, clean_summary, signature

DEFAULT_PORT = 8767
PAIR_SECONDS = 600
MAX_DEVICES = 10
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
API = "/phone/v1"
FIREWALL_RULE = "Windows Maintenance Manager - phone console"
SIG_HEADER, TIME_HEADER, NONCE_HEADER, DEVICE_HEADER = "X-WMM-Phone-Sig", "X-WMM-Phone-Time", "X-WMM-Phone-Nonce", "X-WMM-Phone-Device"


class PhoneError(ValueError):
    """Invalid settings."""


def normalize(codice: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(codice or "").upper())


def lan_addresses() -> List[str]:
    indirizzi = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ipaddress.ip_address(ip).is_private and not ip.startswith("127."):
                indirizzi.add(ip)
    except OSError:
        pass
    return sorted(indirizzi)


class Phones:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seen = {}

    def _read(self) -> dict:
        try:
            dati = json.loads(self.path.read_text(encoding="utf-8"))
            return dati if isinstance(dati, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, dati: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dati), encoding="utf-8")

    def state(self) -> dict:
        dati = self._read()
        attesa = dati.get("pending") or {}
        return {"enabled": bool(dati.get("enabled")), "port": int(dati.get("port") or DEFAULT_PORT),
                "devices": [{k: d.get(k) for k in ("id", "name", "paired", "last_seen")} for d in dati.get("devices", [])],
                "pairing_until": attesa.get("expires_iso") if attesa.get("expires", 0) > time.time() else None,
                "addresses": lan_addresses()}

    def configure(self, attivo, porta=None) -> dict:
        if not isinstance(attivo, bool):
            raise PhoneError("'enabled' must be true or false.")
        if porta is not None and (isinstance(porta, bool) or not isinstance(porta, int) or not 1024 <= porta <= 65535):
            raise PhoneError("The port must be a number from 1024 to 65535.")
        with self._lock:
            dati = self._read()
            dati["enabled"] = attivo
            if porta is not None:
                dati["port"] = porta
            self._write(dati)
        return self.state()

    def new_code(self, now: Optional[float] = None) -> str:
        """A one-time pairing code (80 bits), shown once in the console; only the newest one is valid."""
        adesso = now or time.time()
        codice = "".join(secrets.choice(ALPHABET) for _ in range(16))
        with self._lock:
            dati = self._read()
            if len(dati.get("devices", [])) >= MAX_DEVICES:
                raise PhoneError(f"At most {MAX_DEVICES} phones: remove one first.")
            dati["pending"] = {"secret": notify.protect(codice), "expires": adesso + PAIR_SECONDS,
                               "expires_iso": datetime.fromtimestamp(adesso + PAIR_SECONDS).isoformat(timespec="seconds")}
            self._write(dati)
        return "-".join(codice[i:i + 4] for i in range(0, 16, 4))

    def remove(self, device_id: str) -> bool:
        with self._lock:
            dati = self._read()
            prima = len(dati.get("devices", []))
            dati["devices"] = [d for d in dati.get("devices", []) if d.get("id") != device_id]
            self._write(dati)
            return len(dati["devices"]) < prima

    def verify(self, metodo: str, percorso: str, device: str, istante: str, nonce: str, corpo: bytes, firma: str, nome: str = "",
               now: Optional[float] = None) -> Optional[str]:
        """The id of the paired phone that signed the request; a valid signature with the pending code pairs it."""
        adesso = now or time.time()
        try:
            eta = abs(adesso - float(istante))
        except (TypeError, ValueError):
            return None
        if not re.fullmatch(r"[0-9a-f]{16,32}", device or "") or not firma or eta > MAX_SKEW or not (8 <= len(nonce or "") <= 64):
            return None
        with self._lock:
            dati = self._read()
            voce = next((d for d in dati.get("devices", []) if d.get("id") == device), None)
            nuovo = False
            if voce is not None:
                segreto = notify.unprotect(voce.get("secret", ""))
            else:
                attesa = dati.get("pending") or {}
                if attesa.get("expires", 0) < adesso:
                    return None
                segreto, nuovo = notify.unprotect(attesa.get("secret", "")), True
            if not segreto or not hmac.compare_digest(signature(segreto, metodo, percorso, istante, nonce, corpo), firma):
                return None
            for vecchio in [n for n, t in self._seen.items() if adesso - t > 2 * MAX_SKEW]:
                del self._seen[vecchio]
            if nonce in self._seen:
                return None
            self._seen[nonce] = adesso
            quando = datetime.fromtimestamp(adesso).isoformat(timespec="seconds")
            if nuovo:
                dati.pop("pending", None)
                dati.setdefault("devices", []).append({"id": device, "name": (nome or "Phone")[:60], "secret": notify.protect(segreto),
                                                       "paired": quando, "last_seen": quando})
            else:
                voce["last_seen"] = quando
            self._write(dati)
            return device


def for_data_dir(data_dir: Path) -> Phones:
    return Phones(Path(data_dir) / "phone.json")


WEB = Path(__file__).resolve().parent.parent / "web"
PAGE_HEADERS = {"Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                           "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def tools_list() -> List[dict]:
    from . import actions
    return [{"id": a.id, "title": a.title, "area": a.area, "kind": a.kind, "minutes": a.minutes}
            for a in actions.CATALOG.values() if allowed("safe", a)]


def phone_server(telefoni: Phones, porta: int, riassunto: Callable[[], dict], problemi: Callable[[], list], avvia: Callable[[list], str],
                 stato: Callable[[str], dict]) -> ThreadingHTTPServer:
    """Serves the phone page and the signed API, only to clients of the local network."""

    class Telefono(BaseHTTPRequestHandler):
        server_version = "WMM-Phone"

        def log_message(self, *argomenti):
            pass

        def _send(self, stato_http: int, corpo: bytes, tipo: str, extra=None) -> None:
            self.send_response(stato_http)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            for k, v in dict(PAGE_HEADERS, **(extra or {})).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, stato_http: int, dati: dict) -> None:
            self._send(stato_http, json.dumps(dati).encode("utf-8"), "application/json")

        def _local(self) -> bool:
            try:
                ip = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                return False
            return ip.is_private or ip.is_loopback or ip.is_link_local

        def _device(self, corpo: bytes) -> Optional[str]:
            h = self.headers
            return telefoni.verify(self.command, self.path, h.get(DEVICE_HEADER, ""), h.get(TIME_HEADER, ""), h.get(NONCE_HEADER, ""), corpo,
                                   h.get(SIG_HEADER, ""), h.get("User-Agent", "")[:60])

        def do_GET(self):  # noqa: N802
            if not self._local():
                self._json(403, {"error": "Only the local network."})
                return
            if self.path in ("/", "/index.html"):
                self._send(200, (WEB / "phone.html").read_bytes(), "text/html; charset=utf-8")
                return
            if self.path == "/phone.js":
                self._send(200, (WEB / "js" / "phone.js").read_bytes(), "application/javascript; charset=utf-8")
                return
            if not self.path.startswith(API + "/"):
                self._json(404, {"error": "Not found."})
                return
            if self._device(b"") is None:
                self._json(403, {"error": "This phone is not paired, or the code is wrong."})
                return
            if self.path == API + "/summary":
                try:
                    elenco = [{"title": str(p.get("title", ""))[:160], "area": p.get("area"), "risk": p.get("risk")} for p in problemi()[:15]]
                except Exception:  # noqa: BLE001
                    elenco = []
                self._json(200, {"summary": clean_summary(riassunto()), "problems": elenco})
            elif self.path == API + "/tools":
                self._json(200, {"tools": tools_list()})
            elif self.path.startswith(API + "/runs/") and re.fullmatch(r"[0-9a-f]{32}", self.path[len(API) + 6:]):
                try:
                    self._json(200, clean_run(stato(self.path[len(API) + 6:])))
                except KeyError:
                    self._json(404, {"error": "Run not found."})
            else:
                self._json(404, {"error": "Not found."})

        def do_POST(self):  # noqa: N802
            if not self._local():
                self._json(403, {"error": "Only the local network."})
                return
            try:
                lunghezza = min(int(self.headers.get("Content-Length") or 0), 16 * 1024)
            except ValueError:
                lunghezza = 0
            corpo = self.rfile.read(lunghezza)
            if self._device(corpo) is None:
                self._json(403, {"error": "This phone is not paired, or the code is wrong."})
                return
            if self.path == API + "/hello":
                self._json(200, {"ok": True})
                return
            if self.path != API + "/runs":
                self._json(404, {"error": "Not found."})
                return
            try:
                ids = [a for a in json.loads(corpo.decode("utf-8")).get("actions", []) if isinstance(a, str)][:20]
            except (ValueError, AttributeError):
                self._json(400, {"error": "Bad request."})
                return
            from . import actions
            vietati = [a for a in ids if not allowed("safe", actions.CATALOG.get(a))]
            if not ids or vietati:
                self._json(403, {"error": "Not allowed from a phone: " + ", ".join(vietati or ["nothing to run"])})
                return
            try:
                self._json(202, {"id": avvia(ids)})
            except Exception as errore:  # noqa: BLE001 - a busy PC answers with its reason
                self._json(409, {"error": str(errore)[:200]})

        def do_PUT(self):  # noqa: N802
            self._json(405, {"error": "Not allowed."})

        do_DELETE = do_PATCH = do_PUT

    server = ThreadingHTTPServer(("0.0.0.0", porta), Telefono)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="wmm-phone", daemon=True).start()
    return server
