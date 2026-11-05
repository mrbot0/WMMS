"""Alerts by email and Telegram when nobody is looking at the console: a scheduled run that failed, a system drive
almost full, new unsafe programs. Passwords and the bot token are encrypted with Windows DPAPI (machine scope, so the
scheduled runs, which work as SYSTEM, can read them too); the same alert is sent at most once a day."""
from __future__ import annotations

import base64
import ctypes
import json
import re
import smtplib
import socket
import ssl
import time
import urllib.request
from ctypes import wintypes
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional

import wmm

EVENTS = {
    "run_failed": "A scheduled run failed",
    "disk_low": "The system drive is almost full",
    "unsafe_apps": "New unsafe programs were found",
    "new_device": "A new device joined the network",
    "bt_follower": "An unknown Bluetooth tracker keeps showing up",
    "config_changed": "Suspicious changes in startup, tasks or extensions",
    "connection_down": "The internet connection dropped",
    "early_warning": "Signs that a part of the PC may fail soon",
}
EVENTS_IT = {
    "run_failed": "Un'esecuzione pianificata non è riuscita", "disk_low": "Il disco di sistema è quasi pieno",
    "unsafe_apps": "Trovati nuovi programmi non sicuri", "new_device": "Un nuovo dispositivo è entrato nella rete",
    "bt_follower": "Un tracker Bluetooth sconosciuto continua a comparire", "config_changed": "Modifiche sospette ad avvio, attività o estensioni",
    "connection_down": "La connessione a internet è caduta", "early_warning": "Segni che una parte del PC potrebbe guastarsi presto",
}
SECRETS = ("telegram_token", "smtp_password")
FIELDS = {
    "telegram_token": 200, "telegram_chat": 64, "smtp_host": 200, "smtp_port": 5, "smtp_user": 200, "smtp_password": 200,
    "smtp_from": 200, "email_to": 400,
}
REPEAT_SECONDS = 24 * 3600
TIMEOUT = 15


class NotifyError(ValueError):
    """Invalid settings or a channel that refused the message."""


# ---------- DPAPI ----------

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


CRYPTPROTECT_UI_FORBIDDEN = 0x1
CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _crypt(dati: bytes, proteggi: bool) -> bytes:
    buffer = ctypes.create_string_buffer(dati, len(dati))
    ingresso = _Blob(len(dati), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    uscita = _Blob()
    funzione = ctypes.windll.crypt32.CryptProtectData if proteggi else ctypes.windll.crypt32.CryptUnprotectData
    flag = CRYPTPROTECT_UI_FORBIDDEN | (CRYPTPROTECT_LOCAL_MACHINE if proteggi else 0)
    if not funzione(ctypes.byref(ingresso), None, None, None, None, flag, ctypes.byref(uscita)):
        raise OSError("Windows could not " + ("protect" if proteggi else "read") + " the secret")
    try:
        return ctypes.string_at(uscita.pbData, uscita.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(uscita.pbData)


def protect(testo: str) -> str:
    return base64.b64encode(_crypt(testo.encode("utf-8"), True)).decode("ascii") if testo else ""


def unprotect(testo: str) -> str:
    try:
        return _crypt(base64.b64decode(testo), False).decode("utf-8") if testo else ""
    except (OSError, ValueError):
        return ""  # another PC or a damaged value: the user types it again


# ---------- settings ----------

class Notifier:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> dict:
        try:
            dati = json.loads(self.path.read_text(encoding="utf-8"))
            return dati if isinstance(dati, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, dati: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dati, indent=1), encoding="utf-8")

    def settings(self) -> dict:
        """What the page shows: every field except the secrets, which only say whether they are set."""
        dati = self._read()
        vista = {k: dati.get(k, "") for k in FIELDS if k not in SECRETS}
        vista.update({f"has_{k}": bool(dati.get(k)) for k in SECRETS})
        vista["events"] = [e for e in dati.get("events", list(EVENTS)) if e in EVENTS]
        vista["event_titles"] = EVENTS
        vista["channels"] = self.all_channels()
        return vista

    def save(self, valori: dict) -> dict:
        if not isinstance(valori, dict):
            raise NotifyError("The settings must be an object.")
        dati = self._read()
        for chiave, massimo in FIELDS.items():
            if chiave not in valori:
                continue
            valore = valori[chiave]
            if not isinstance(valore, str) or len(valore) > massimo:
                raise NotifyError(f"{chiave} must be text of at most {massimo} characters.")
            valore = valore.strip()
            if chiave in SECRETS:
                if valore:  # an empty secret field means "keep the saved one"
                    dati[chiave] = protect(valore)
                continue
            dati[chiave] = valore
        if valori.get("clear_secrets") is True:
            for chiave in SECRETS:
                dati.pop(chiave, None)
        if "events" in valori:
            if not isinstance(valori["events"], list) or not all(e in EVENTS for e in valori["events"]):
                raise NotifyError("Unknown event.")
            dati["events"] = list(valori["events"])
        if dati.get("smtp_port") and not re.fullmatch(r"\d{2,5}", dati["smtp_port"]):
            raise NotifyError("The SMTP port must be a number (587 or 465).")
        if dati.get("email_to") and not all(re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", a.strip()) for a in dati["email_to"].split(",")):
            raise NotifyError("Write the recipients as name@domain, separated by commas.")
        if dati.get("telegram_chat") and not re.fullmatch(r"-?\d{3,20}|@\w{4,40}", dati["telegram_chat"]):
            raise NotifyError("The Telegram chat is a number (e.g. 123456789) or @channelname.")
        self._write(dati)
        return self.settings()

    @staticmethod
    def channels(dati: dict) -> List[str]:
        canali = []
        if dati.get("telegram_token") and dati.get("telegram_chat"):
            canali.append("telegram")
        if dati.get("smtp_host") and dati.get("email_to"):
            canali.append("email")
        return canali

    # ---------- sending ----------

    @property
    def data_dir(self) -> Path:
        return self.path.parent

    def all_channels(self) -> List[str]:
        """E-mail and Telegram from these settings, the webhook from the app settings (2.9)."""
        from . import appsettings
        canali = self.channels(self._read())
        if appsettings.load(self.data_dir)["webhook_url"]:
            canali.append("webhook")
        return canali

    def _role_contacts(self) -> tuple:
        """E-mail addresses and Telegram chats of the active users of the roles chosen in Settings › Alerts."""
        from . import appsettings
        ruoli = set(appsettings.load(self.data_dir)["alert_roles"])
        if not ruoli or not (self.data_dir / "accounts.db").exists():
            return [], []
        try:
            from .accounts import for_data_dir
            utenti = [u for u in for_data_dir(self.data_dir).users() if u["role_id"] in ruoli and u["status"] == "active"]
        except Exception:  # noqa: BLE001 - alerts still go to the main recipients
            return [], []
        return [u["email"] for u in utenti if u["email"]], [u["telegram"] for u in utenti if u["telegram"]]

    def send(self, titolo: str, testo: str, solo: Optional[List[str]] = None, evento: str = "") -> Dict[str, str]:
        """Sends to every configured channel (or only to `solo`); returns channel -> "ok" or the error."""
        from . import appsettings
        dati = self._read()
        app = appsettings.load(self.data_dir)
        esiti: Dict[str, str] = {}
        if app["alert_prefix"]:
            titolo = f"[{app['alert_prefix']}] {titolo}"
        corpo = f"{titolo}\n\n{testo}\n\n— Windows Maintenance Manager {wmm.VERSION}"
        canali = [c for c in self.all_channels() if solo is None or c in solo]
        email_extra, chat_extra = self._role_contacts() if solo is None else ([], [])
        if "telegram" in canali:
            if not appsettings.allowed(self.data_dir, "telegram"):
                esiti["telegram"] = "turned off (Settings › Connections)"
            else:
                token = unprotect(dati["telegram_token"])
                esiti["telegram"] = self._telegram(token, dati["telegram_chat"], corpo)
                for chat in sorted(set(chat_extra) - {dati["telegram_chat"]}):
                    self._telegram(token, chat, corpo)
        if "email" in canali:
            if email_extra:
                dati = dict(dati, email_to=", ".join(dict.fromkeys([dati["email_to"]] + email_extra)))
            esiti["email"] = self._email(dati, titolo, corpo)
        if "webhook" in canali:
            esiti["webhook"] = appsettings.webhook_send(app["webhook_url"], app["webhook_kind"], titolo, testo) \
                if appsettings.allowed(self.data_dir, "webhook") else "turned off (Settings › Connections)"
        appsettings.log_alert(self.data_dir, evento or "manual", titolo, esiti)
        return esiti

    @staticmethod
    def _telegram(token: str, chat: str, testo: str) -> str:
        if not re.fullmatch(r"\d{5,15}:[\w-]{20,100}", token or ""):
            return "the bot token is not valid (type it again)"
        richiesta = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                           data=json.dumps({"chat_id": chat, "text": testo[:4000]}).encode("utf-8"),
                                           headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
                return "ok" if json.loads(risposta.read(65536)).get("ok") else "Telegram refused the message"
        except Exception as errore:  # network, HTTP 4xx/5xx: one line for the page, never the token
            return re.sub(r"bot\d+:[\w-]+", "bot***", str(errore))[:200]

    @staticmethod
    def _email(dati: dict, titolo: str, testo: str) -> str:
        messaggio = EmailMessage()
        messaggio["Subject"] = titolo
        messaggio["From"] = dati.get("smtp_from") or dati.get("smtp_user") or "wmm@localhost"
        messaggio["To"] = dati["email_to"]
        messaggio.set_content(testo)
        porta = int(dati.get("smtp_port") or 587)
        contesto = ssl.create_default_context()
        try:
            if porta == 465:
                server = smtplib.SMTP_SSL(dati["smtp_host"], porta, timeout=TIMEOUT, context=contesto)
            else:
                server = smtplib.SMTP(dati["smtp_host"], porta, timeout=TIMEOUT)
                server.starttls(context=contesto)  # never send a password in clear text
            with server:
                if dati.get("smtp_user"):
                    server.login(dati["smtp_user"], unprotect(dati.get("smtp_password", "")))
                server.send_message(messaggio)
            return "ok"
        except (OSError, smtplib.SMTPException) as errore:
            return str(errore)[:200]

    def event(self, chiave: str, dettaglio: str, quando: Optional[float] = None, gruppo: str = "") -> Dict[str, str]:
        """An alert for one event, unless it is turned off or the same alert went out in the last 24 hours."""
        from . import appsettings
        dati = self._read()
        if chiave not in EVENTS or chiave not in dati.get("events", list(EVENTS)) or not self.all_channels():
            return {}
        app = appsettings.load(self.data_dir)
        adesso = quando or time.time()
        nome = f"{chiave}:{gruppo}"
        ultimo = dati.get("sent", {}).get(nome)
        if ultimo is not None and adesso - float(ultimo) < app["alert_repeat_hours"] * 3600:
            return {}
        it = app["alert_lang"] == "it"
        pc = app["pc_label"] or socket.gethostname()
        titolo = f"{EVENTS_IT.get(chiave, EVENTS[chiave])} su {pc}" if it else f"{EVENTS[chiave]} on {pc}"
        if appsettings.in_quiet(app["alert_quiet"], adesso):
            appsettings.log_alert(self.data_dir, chiave, titolo, {}, "quiet hours")
            return {}
        canali = app["alert_routes"].get(chiave)
        esiti = self.send(titolo, dettaglio, solo=canali if canali is not None else None, evento=chiave)
        if any(v == "ok" for v in esiti.values()):
            dati = self._read()
            dati.setdefault("sent", {})[nome] = adesso
            self._write(dati)
        return esiti


def for_data_dir(data_dir: Path) -> Notifier:
    return Notifier(Path(data_dir) / "notifications.json")


def safe_event(data_dir: Path, chiave: str, dettaglio: str, gruppo: str = "") -> None:
    """For the places that report events: an alert that cannot go out never breaks a scan or a run."""
    try:
        for_data_dir(data_dir).event(chiave, dettaglio, gruppo=gruppo)
    except Exception:  # noqa: BLE001 - alerts are best effort by design
        pass
