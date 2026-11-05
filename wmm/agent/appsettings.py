"""Settings of the app that the agent itself applies (2.9), next to the console preferences kept in the browser:
organization, port, proxy and offline mode for every outgoing connection, maintenance window and safety rules for runs,
data retention, the networks allowed to reach the phone console and the PC sharing, and the alert rules (language,
subject prefix, repeat interval, quiet hours, routing per event, webhook, alerts to the users of chosen roles).
Also: SMTP presets, Telegram bot check and chat detection, the alert history, database maintenance, configuration
backup and restore, and a diagnostic bundle. Stored in dati/app_settings.json; secrets never leave this PC."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import wmm
from . import securestore

DEFAULTS: Dict[str, object] = {
    # app
    "org_name": "", "pc_label": "", "console_port": 0, "default_user_lang": "it", "update_check_on_start": False,
    # connections
    "proxy_url": "", "proxy_bypass": "", "offline": False, "allow_update_check": True, "allow_kev": True, "allow_virustotal": True,
    "allow_assistant": True, "allow_telegram": True, "allow_webhook": True, "lan_allow": "",
    # runs
    "maint_window": {"enabled": False, "days": [0, 1, 2, 3, 4, 5, 6], "from": "22:00", "to": "06:00"},
    "block_high_risk": False, "require_reason": False, "confirm_high_with_name": False, "approval_levels": [], "auto_rollback": False,
    "https_lan": False, "encrypt_data": False,
    # data
    "retention": {"history_days": 0, "connection_days": 90, "snapshots_days": 90, "notify_log_days": 90},
    # alerts
    "alert_lang": "en", "alert_prefix": "", "alert_repeat_hours": 24, "alert_quiet": {"enabled": False, "from": "22:00", "to": "07:00"},
    "alert_routes": {}, "alert_roles": [], "webhook_url": "", "webhook_kind": "generic",
    # automation (2.12)
    "automation_rules": [], "goals": [], "winget_exclusions": [], "file_backup": {"target": "", "folders": ["Documents", "Desktop", "Pictures"]},
}
SECTIONS = {
    "app": ["org_name", "pc_label", "console_port", "default_user_lang", "update_check_on_start"],
    "connections": ["proxy_url", "proxy_bypass", "offline", "allow_update_check", "allow_kev", "allow_virustotal", "allow_assistant", "allow_telegram",
                    "allow_webhook", "lan_allow"],
    "runs": ["maint_window", "block_high_risk", "require_reason", "confirm_high_with_name", "approval_levels", "auto_rollback"],
    "security": ["https_lan", "encrypt_data"],
    "data": ["retention"],
    "alerts": ["alert_lang", "alert_prefix", "alert_repeat_hours", "alert_quiet", "alert_routes", "alert_roles", "webhook_url", "webhook_kind"],
    "automation": ["automation_rules", "goals", "winget_exclusions", "file_backup"],
}
SERVICES = ("update_check", "kev", "virustotal", "assistant", "telegram", "webhook")
CHANNELS = ("email", "telegram", "webhook")
WEBHOOK_KINDS = ("generic", "teams", "slack", "discord")
SMTP_PRESETS = [
    {"id": "gmail", "name": "Gmail / Google Workspace", "host": "smtp.gmail.com", "port": "587", "note": "Use an app password (Google account › Security)."},
    {"id": "outlook", "name": "Outlook.com / Hotmail", "host": "smtp-mail.outlook.com", "port": "587", "note": "Needs SMTP AUTH turned on for the account."},
    {"id": "m365", "name": "Microsoft 365 (work account)", "host": "smtp.office365.com", "port": "587", "note": "The tenant must allow SMTP AUTH for the mailbox."},
    {"id": "icloud", "name": "iCloud Mail", "host": "smtp.mail.me.com", "port": "587", "note": "Use an app-specific password."},
    {"id": "yahoo", "name": "Yahoo Mail", "host": "smtp.mail.yahoo.com", "port": "465", "note": "Use an app password."},
    {"id": "libero", "name": "Libero Mail", "host": "smtp.libero.it", "port": "465", "note": ""},
    {"id": "aruba", "name": "Aruba (PEC excluded)", "host": "smtps.aruba.it", "port": "465", "note": ""},
    {"id": "register", "name": "Register.it", "host": "authsmtp.securemail.pro", "port": "465", "note": ""},
    {"id": "tim", "name": "TIM / Alice", "host": "smtp.tim.it", "port": "587", "note": ""},
    {"id": "fastweb", "name": "Fastweb", "host": "smtp.fastwebnet.it", "port": "587", "note": ""},
]
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_LOCK = threading.Lock()


class SettingsError(ValueError):
    """An invalid value, shown as it is."""


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "app_settings.json"


def load(data_dir: Path) -> dict:
    try:
        salvati = json.loads(securestore.read_text(_path(data_dir)))
        salvati = salvati if isinstance(salvati, dict) else {}
    except (OSError, ValueError):
        salvati = {}
    valori = {}
    for k, v in DEFAULTS.items():
        valori[k] = dict(v, **salvati[k]) if isinstance(v, dict) and isinstance(salvati.get(k), dict) and k != "alert_routes" else salvati.get(k, v)
    return valori


def _window(v, campo: str) -> dict:
    if not isinstance(v, dict):
        raise SettingsError(f"{campo}: an object.")
    pulito = {"enabled": bool(v.get("enabled"))}
    for k in ("from", "to"):
        if not TIME.fullmatch(str(v.get(k, ""))):
            raise SettingsError(f"{campo}: times as HH:MM.")
        pulito[k] = v[k]
    if "days" in DEFAULTS.get(campo, {}):
        giorni = v.get("days", [])
        if not isinstance(giorni, list) or not giorni or any(g not in range(7) for g in giorni):
            raise SettingsError(f"{campo}: choose at least one day.")
        pulito["days"] = sorted(set(giorni))
    return pulito


def validate(chiave: str, v, accounts=None):
    if chiave not in DEFAULTS:
        raise SettingsError(f"Unknown setting: {chiave}")
    if chiave in SECTIONS["automation"]:  # 2.12
        from . import actions, notify, plus212
        try:
            if chiave == "automation_rules":
                return plus212.clean_rules(v, actions.CATALOG, notify.EVENTS)
            if chiave == "goals":
                return plus212.clean_goals(v)
            if chiave == "file_backup":
                return plus212.backup_settings_clean(v if isinstance(v, dict) else {})
        except ValueError as e:
            raise SettingsError(str(e)) from None
        if not isinstance(v, list) or len(v) > 200 or any(not isinstance(x, str) or not re.fullmatch(r"[\w.\-+]{2,100}", x) for x in v):
            raise SettingsError("winget IDs, one per line (for example 7zip.7zip).")
        return sorted(set(v))
    base = DEFAULTS[chiave]
    if isinstance(base, bool):
        if not isinstance(v, bool):
            raise SettingsError(f"{chiave}: true or false.")
        return v
    if chiave in ("org_name", "pc_label", "alert_prefix"):
        if not isinstance(v, str) or len(v) > 60:
            raise SettingsError(f"{chiave}: text of at most 60 characters.")
        return v.strip()
    if chiave == "console_port":
        if isinstance(v, bool) or not isinstance(v, int) or not (v == 0 or 1024 <= v <= 65535):
            raise SettingsError("The console port is 0 (default) or a number from 1024 to 65535.")
        return v
    if chiave in ("default_user_lang", "alert_lang"):
        if v not in ("it", "en"):
            raise SettingsError("Language: it or en.")
        return v
    if chiave == "proxy_url":
        if not isinstance(v, str) or (v and not re.fullmatch(r"https?://[\w.\-]+(:\d{2,5})?/?", v.strip())):
            raise SettingsError("The proxy is an address like http://proxy.company.local:8080 (no user or password in it).")
        return v.strip()
    if chiave == "proxy_bypass":
        if not isinstance(v, str) or len(v) > 300 or not re.fullmatch(r"[\w.\-*,; ]*", v):
            raise SettingsError("Proxy exceptions: host names separated by commas.")
        return v.strip()
    if chiave == "lan_allow":
        if not isinstance(v, str) or len(v) > 300:
            raise SettingsError("Allowed networks: addresses like 192.168.1.0/24, separated by commas.")
        for parte in [p.strip() for p in v.split(",") if p.strip()]:
            try:
                rete = ipaddress.ip_network(parte, strict=False)
            except ValueError:
                raise SettingsError(f"{parte} is not a network (e.g. 192.168.1.0/24).") from None
            if not (rete.is_private or rete.is_loopback):
                raise SettingsError(f"{parte} is not a private network.")
        return v.strip()
    if chiave == "maint_window" or chiave == "alert_quiet":
        return _window(v, chiave)
    if chiave == "retention":
        if not isinstance(v, dict):
            raise SettingsError("Retention: an object.")
        pulito = {}
        for k, predefinito in DEFAULTS["retention"].items():
            n = v.get(k, predefinito)
            if isinstance(n, bool) or not isinstance(n, int) or not (n == 0 or 7 <= n <= 3650):
                raise SettingsError(f"{k}: 0 (keep everything) or 7 to 3650 days.")
            pulito[k] = n
        return pulito
    if chiave == "alert_repeat_hours":
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 168:
            raise SettingsError("Repeat the same alert after 1 to 168 hours.")
        return v
    if chiave == "alert_routes":
        from . import notify
        if not isinstance(v, dict) or any(e not in notify.EVENTS for e in v) or \
                any(not isinstance(c, list) or any(x not in CHANNELS for x in c) for c in v.values()):
            raise SettingsError("Routing: for each event, a list of channels (email, telegram, webhook).")
        return {e: sorted(set(c)) for e, c in v.items()}
    if chiave == "approval_levels":
        if not isinstance(v, list) or any(x not in ("moderate", "high") for x in v):
            raise SettingsError("Approval: a list with moderate and/or high.")
        return sorted(set(v))
    if chiave == "alert_roles":
        if not isinstance(v, list) or not all(isinstance(r, str) for r in v):
            raise SettingsError("Roles: a list.")
        if accounts is not None:
            noti = {r["id"] for r in accounts.roles()}
            if any(r not in noti for r in v):
                raise SettingsError("Unknown role.")
        return sorted(set(v))
    if chiave == "webhook_url":
        if not isinstance(v, str) or (v and not re.fullmatch(r"https://[^\s]{8,500}", v.strip())):
            raise SettingsError("The webhook is an https:// address.")
        return v.strip()
    if chiave == "webhook_kind":
        if v not in WEBHOOK_KINDS:
            raise SettingsError("Webhook kind: generic, teams, slack or discord.")
        return v
    raise SettingsError(f"Unknown setting: {chiave}")


def save(data_dir: Path, valori: dict, accounts=None) -> dict:
    if not isinstance(valori, dict) or not valori:
        raise SettingsError("Nothing to save.")
    puliti = {k: validate(k, v, accounts) for k, v in valori.items()}
    with _LOCK:
        try:
            salvati = json.loads(securestore.read_text(_path(data_dir)))
            salvati = salvati if isinstance(salvati, dict) else {}
        except (OSError, ValueError):
            salvati = {}
        salvati.update(puliti)
        _path(data_dir).parent.mkdir(parents=True, exist_ok=True)
        securestore.write_text(_path(data_dir), json.dumps(salvati, indent=1, ensure_ascii=False), encoding="utf-8")
    if {"proxy_url", "proxy_bypass"} & set(puliti):
        apply_proxy(data_dir)
    return load(data_dir)


def reset(data_dir: Path, sezione: str) -> dict:
    if sezione not in SECTIONS and sezione != "all":
        raise SettingsError("Unknown section.")
    chiavi = [k for s in SECTIONS.values() for k in s] if sezione == "all" else SECTIONS[sezione]
    with _LOCK:
        try:
            salvati = json.loads(securestore.read_text(_path(data_dir)))
        except (OSError, ValueError):
            salvati = {}
        for k in chiavi:
            salvati.pop(k, None)
        securestore.write_text(_path(data_dir), json.dumps(salvati, indent=1, ensure_ascii=False), encoding="utf-8")
    apply_proxy(data_dir)
    return load(data_dir)


# ---------- what the settings change ----------

def allowed(data_dir: Path, servizio: str) -> bool:
    """Outgoing connections: off for every service in offline mode, or for one service."""
    s = load(data_dir)
    return not s["offline"] and bool(s.get(f"allow_{servizio}", True))


def apply_proxy(data_dir: Path) -> None:
    """urllib (alerts, updates, catalogs, VirusTotal) and the assistant use the proxy; SMTP connects directly."""
    s = load(data_dir)
    for nome in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        os.environ.pop(nome, None)
    if s["proxy_url"]:
        os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = s["proxy_url"]
        os.environ["NO_PROXY"] = ",".join(["localhost", "127.0.0.1"] + [h.strip() for h in re.split(r"[,;]", s["proxy_bypass"]) if h.strip()])
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({"http": s["proxy_url"], "https": s["proxy_url"]})))
    else:
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def in_window(finestra: dict, t: Optional[float] = None) -> bool:
    if not finestra.get("enabled"):
        return True
    momento = datetime.fromtimestamp(t if t is not None else time.time())
    ora = momento.strftime("%H:%M")
    if finestra["from"] < finestra["to"]:
        return momento.weekday() in finestra["days"] and finestra["from"] <= ora < finestra["to"]
    if ora >= finestra["from"]:
        return momento.weekday() in finestra["days"]
    return ora < finestra["to"] and (momento.weekday() - 1) % 7 in finestra["days"]


def in_quiet(quiete: dict, t: Optional[float] = None) -> bool:
    if not quiete.get("enabled"):
        return False
    ora = datetime.fromtimestamp(t if t is not None else time.time()).strftime("%H:%M")
    if quiete["from"] < quiete["to"]:
        return quiete["from"] <= ora < quiete["to"]
    return ora >= quiete["from"] or ora < quiete["to"]


def lan_allowed(data_dir: Path, ip: str) -> bool:
    """The phone console and the PC sharing answer only these networks, when a list is set."""
    reti = [p.strip() for p in load(data_dir)["lan_allow"].split(",") if p.strip()]
    if not reti:
        return True
    try:
        indirizzo = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return indirizzo.is_loopback or any(indirizzo in ipaddress.ip_network(r, strict=False) for r in reti)


# ---------- alert history ----------

def _log_path(data_dir: Path) -> Path:
    return Path(data_dir) / "notify_log.json"


def log_alert(data_dir: Path, evento: str, titolo: str, esiti: Dict[str, str], saltato: str = "") -> None:
    with _LOCK:
        try:
            voci = json.loads(securestore.read_text(_log_path(data_dir)))
        except (OSError, ValueError):
            voci = []
        voci.append({"at": datetime.now().isoformat(timespec="seconds"), "event": evento, "title": titolo[:200], "results": esiti, "skipped": saltato})
        try:
            securestore.write_text(_log_path(data_dir), json.dumps(voci[-500:], ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def alert_log(data_dir: Path) -> List[dict]:
    try:
        return list(reversed(json.loads(securestore.read_text(_log_path(data_dir)))))
    except (OSError, ValueError):
        return []


def clear_alert_log(data_dir: Path) -> None:
    try:
        _log_path(data_dir).unlink()
    except OSError:
        pass


# ---------- Telegram and webhooks ----------

def _get_json(url: str, timeout: int = 15, opener=None) -> dict:
    with (opener or urllib.request.urlopen)(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
        return json.loads(r.read(256 * 1024).decode("utf-8"))


def telegram_bot(token: str, opener=None) -> dict:
    """The bot behind a token (getMe): its name, to be sure the token is the right one."""
    if not re.fullmatch(r"\d{5,15}:[\w-]{20,100}", token or ""):
        raise SettingsError("The bot token is not valid: copy it again from @BotFather.")
    try:
        dati = _get_json(f"https://api.telegram.org/bot{token}/getMe", opener=opener)
    except urllib.error.HTTPError as e:
        raise SettingsError("Telegram refused the token." if e.code in (401, 404) else f"Telegram answered HTTP {e.code}.") from None
    except (OSError, ValueError) as e:
        raise SettingsError(f"Telegram is not reachable ({getattr(e, 'reason', e)}).") from None
    bot = dati.get("result") or {}
    return {"name": bot.get("first_name", ""), "username": bot.get("username", ""), "id": bot.get("id")}


def telegram_chats(token: str, opener=None) -> List[dict]:
    """The chats that wrote to the bot recently (getUpdates): send any message to the bot first."""
    if not re.fullmatch(r"\d{5,15}:[\w-]{20,100}", token or ""):
        raise SettingsError("The bot token is not valid: copy it again from @BotFather.")
    try:
        dati = _get_json(f"https://api.telegram.org/bot{token}/getUpdates?limit=50", opener=opener)
    except urllib.error.HTTPError as e:
        raise SettingsError("Telegram refused the token." if e.code in (401, 404) else
                            "The bot has a webhook set: chats cannot be read." if e.code == 409 else f"Telegram answered HTTP {e.code}.") from None
    except (OSError, ValueError) as e:
        raise SettingsError(f"Telegram is not reachable ({getattr(e, 'reason', e)}).") from None
    chat = {}
    for u in dati.get("result", []):
        messaggio = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        c = messaggio.get("chat") or {}
        if c.get("id") is not None:
            nome = c.get("title") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or c.get("username") or ""
            chat[c["id"]] = {"id": str(c["id"]), "name": nome[:80], "type": c.get("type", "")}
    return list(chat.values())


def webhook_payload(tipo: str, titolo: str, testo: str) -> dict:
    if tipo == "slack":
        return {"text": f"*{titolo}*\n{testo}"[:3900]}
    if tipo == "teams":
        return {"text": f"**{titolo}**\n\n{testo}"[:20000]}
    if tipo == "discord":
        return {"content": f"**{titolo}**\n{testo}"[:1900]}
    return {"title": titolo, "text": testo, "app": wmm.APP_NAME, "version": wmm.VERSION}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *argomenti, **opzioni):
        return None  # a webhook that redirects is not followed: the new address was never checked


def public_https(url: str) -> Optional[str]:
    """Why a webhook address cannot be used, or None: https only, and a name that resolves only to public addresses
    (never this PC, the local network or link-local services)."""
    import socket
    import urllib.parse
    parti = urllib.parse.urlparse(url or "")
    if parti.scheme != "https" or not parti.hostname:
        return "not an https:// address"
    try:
        indirizzi = {info[4][0] for info in socket.getaddrinfo(parti.hostname, parti.port or 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return "the name cannot be resolved"
    for a in indirizzi:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return "the address is not public"
    return None


def webhook_send(url: str, tipo: str, titolo: str, testo: str, opener=None) -> str:
    if not re.fullmatch(r"https://[^\s]{8,500}", url or ""):
        return "no webhook address"
    if opener is None:
        motivo = public_https(url)
        if motivo:
            return motivo
        opener = urllib.request.build_opener(_NoRedirect).open
    richiesta = urllib.request.Request(url, data=json.dumps(webhook_payload(tipo, titolo, testo)).encode("utf-8"),
                                       headers={"Content-Type": "application/json", "User-Agent": f"WMM/{wmm.VERSION}"}, method="POST")
    try:
        with opener(richiesta, timeout=15) as r:
            return "ok" if 200 <= r.status < 300 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except OSError as e:
        return str(getattr(e, "reason", e))[:200]


# ---------- data ----------

DATA_FILES = ("wmm.db", "accounts.db", "central.db", "app_settings.json", "notifications.json", "notify_log.json", "connection_history.json", "wifi_history.json",
              "health_history.json", "drift.json", "suspicious.json", "kev.json", "fleet.json", "phone.json", "custom_tools.json", "digest.json")


def data_info(data_dir: Path) -> dict:
    cartella = Path(data_dir)
    voci = []
    for nome in DATA_FILES:
        p = cartella / nome
        if p.exists():
            voci.append({"name": nome, "bytes": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    snapshot = list((cartella / "drift_snapshots").glob("*.json")) if (cartella / "drift_snapshots").exists() else []
    if snapshot:
        voci.append({"name": "drift_snapshots", "bytes": sum(p.stat().st_size for p in snapshot), "files": len(snapshot)})
    from . import migrations
    return {"folder": str(cartella), "files": voci, "total_bytes": sum(v["bytes"] for v in voci), "databases": migrations.status(cartella)}


def db_maintenance(data_dir: Path, azione: str) -> List[dict]:
    """integrity: PRAGMA integrity_check; compact: VACUUM (frees the space of deleted history)."""
    if azione not in ("integrity", "compact"):
        raise SettingsError("Unknown action.")
    esiti = []
    for nome in ("wmm.db", "accounts.db", "central.db"):
        p = Path(data_dir) / nome
        if not p.exists():
            continue
        prima = p.stat().st_size
        db = sqlite3.connect(p, timeout=10)
        try:
            if azione == "integrity":
                esito = db.execute("PRAGMA integrity_check").fetchone()[0]
            else:
                db.execute("VACUUM")
                esito = "ok"
        except sqlite3.Error as e:
            esito = str(e)
        finally:
            db.close()
        esiti.append({"name": nome, "result": esito, "before": prima, "after": p.stat().st_size})
    return esiti


def retention_run(data_dir: Path, store=None, machine_id: str = "", accounts=None, now: Optional[datetime] = None) -> dict:
    """Deletes what is older than the retention of each kind of data."""
    r = load(data_dir)["retention"]
    adesso = now or datetime.now()
    fatto = {}
    if r["history_days"] and store is not None:
        fatto["history"] = store.prune_runs(machine_id, r["history_days"])
    if r["connection_days"]:
        p = Path(data_dir) / "connection_history.json"
        try:
            dati = json.loads(securestore.read_text(p))
            limite = (adesso - timedelta(days=r["connection_days"])).isoformat(timespec="seconds")
            prima = len(dati.get("samples", []))
            dati["samples"] = [c for c in dati.get("samples", []) if str(c.get("t", "")) >= limite]
            securestore.write_text(p, json.dumps(dati), encoding="utf-8")
            fatto["connection"] = prima - len(dati["samples"])
        except (OSError, ValueError):
            pass
    if r["snapshots_days"]:
        limite = (adesso - timedelta(days=r["snapshots_days"])).date().isoformat()
        n = 0
        for p in (Path(data_dir) / "drift_snapshots").glob("????-??-??.json"):
            if p.stem < limite:
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        fatto["snapshots"] = n
    if r["notify_log_days"]:
        limite = (adesso - timedelta(days=r["notify_log_days"])).isoformat(timespec="seconds")
        voci = list(reversed(alert_log(data_dir)))
        rimaste = [v for v in voci if v.get("at", "") >= limite]
        if len(rimaste) != len(voci):
            securestore.write_text(_log_path(data_dir), json.dumps(rimaste, ensure_ascii=False), encoding="utf-8")
        fatto["alerts"] = len(voci) - len(rimaste)
    if accounts is not None:
        fatto["audit"] = accounts.audit_prune()
    return fatto


# ---------- backup and restore ----------

def export_config(data_dir: Path, store=None, accounts=None) -> dict:
    """Everything that configures the app, without passwords, tokens, keys or history."""
    from . import notify
    notifiche = notify.for_data_dir(data_dir).settings()
    copia = {"format": "wmm-config/1", "version": wmm.VERSION, "created": datetime.now().isoformat(timespec="seconds"),
             "app_settings": load(data_dir),
             "notifications": {k: v for k, v in notifiche.items() if k in notify.FIELDS or k == "events"},
             "settings": store.settings() if store is not None else {}}
    if accounts is not None:
        copia["roles"] = [accounts.export_role(r["id"]) | {"id": r["id"], "builtin": r["builtin"]} for r in accounts.roles()]
        copia["account_policy"] = accounts.policy()
    try:
        copia["custom_tools"] = json.loads((Path(data_dir) / "custom_tools.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return copia


def import_config(data_dir: Path, dati: dict, store=None, accounts=None, by: str = "", user: Optional[dict] = None) -> dict:
    """Puts back the chosen parts of a backup. Secrets are not in a backup and stay as they are."""
    from . import notify
    if not isinstance(dati, dict) or dati.get("format") != "wmm-config/1":
        raise SettingsError("Not a backup of Windows Maintenance Manager.")
    fatto, saltato = [], []

    def puo(permesso: str) -> bool:
        return user is None or permesso in user.get("permissions", ())
    if isinstance(dati.get("app_settings"), dict) and not puo("settings.edit"):
        dati = dict(dati, app_settings=None)
        saltato.append("app_settings")
    if isinstance(dati.get("notifications"), dict) and not puo("notifications.manage"):
        dati = dict(dati, notifications=None)
        saltato.append("notifications")
    if isinstance(dati.get("roles"), list) and not puo("roles.manage"):
        dati = dict(dati, roles=None)
        saltato.append("roles")
    if isinstance(dati.get("account_policy"), dict) and not puo("settings.security"):
        dati = dict(dati, account_policy=None)
        saltato.append("account_policy")
    if dati.get("custom_tools") and not puo("custom_tools.manage"):
        dati = dict(dati, custom_tools=None)
        saltato.append("custom_tools")
    if isinstance(dati.get("app_settings"), dict):
        save(data_dir, {k: v for k, v in dati["app_settings"].items() if k in DEFAULTS}, accounts)
        fatto.append("app_settings")
    if isinstance(dati.get("notifications"), dict):
        notify.for_data_dir(data_dir).save({k: v for k, v in dati["notifications"].items() if (k in notify.FIELDS and k not in notify.SECRETS) or k == "events"})
        fatto.append("notifications")
    if isinstance(dati.get("settings"), dict) and store is not None:
        store.save_settings({k: v for k, v in dati["settings"].items() if isinstance(v, str)})
        fatto.append("settings")
    if accounts is not None and isinstance(dati.get("roles"), list):
        nomi = {r["name"].lower() for r in accounts.roles()}
        for r in dati["roles"]:
            if not r.get("builtin") and isinstance(r.get("name"), str) and r["name"].lower() not in nomi:
                accounts.import_role({k: r[k] for k in ("format", "name", "description", "color", "permissions", "require_2fa") if k in r}, by, user)
        fatto.append("roles")
    if accounts is not None and isinstance(dati.get("account_policy"), dict):
        accounts.set_policy({k: v for k, v in dati["account_policy"].items() if k != "enabled"}, by)
        fatto.append("account_policy")
    if isinstance(dati.get("custom_tools"), list):
        from . import custom_tools
        esistenti = {t.get("title") for t in custom_tools.load(data_dir)}
        for voce in dati["custom_tools"]:
            if isinstance(voce, dict) and voce.get("title") not in esistenti:
                try:
                    custom_tools.save(data_dir, {k: v for k, v in voce.items() if k != "id"})  # the same checks as the Toolbox form
                except (custom_tools.CustomToolError, KeyError):
                    saltato.append(f"custom tool {voce.get('title')}")
        fatto.append("custom_tools")
    return {"restored": fatto, "skipped": saltato}


def diagnostics(data_dir: Path, health: Optional[dict] = None, info: Optional[dict] = None) -> dict:
    """What support needs, without secrets or personal data."""
    import platform
    import sys
    s = load(data_dir)
    return {"format": "wmm-diagnostics/1", "created": datetime.now().isoformat(timespec="seconds"), "version": wmm.VERSION,
            "python": sys.version.split()[0], "windows": platform.platform(), "info": {k: v for k, v in (info or {}).items() if k not in ("machine_id",)},
            "health": health or {}, "data": data_info(data_dir),
            "settings": {k: ("set" if k in ("proxy_url", "webhook_url") and v else v) for k, v in s.items()}}
