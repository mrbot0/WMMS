"""Tickets (2.10): alerts can open a ticket in Jira, ServiceNow, GLPI or any service that accepts JSON, and the number
comes back to the console (Incidents) and to the audit log. Credentials are kept encrypted for this Windows user;
only https addresses; nothing is sent while the integration is off or the PC is offline."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Optional

from . import governance, notify

KINDS = ("jira", "servicenow", "glpi", "generic")


def settings(data_dir) -> dict:
    s = governance.load_settings(data_dir).get("tickets") or {}
    return {"kind": s.get("kind", ""), "url": s.get("url", ""), "user": s.get("user", ""), "project": s.get("project", ""),
            "issue_type": s.get("issue_type", "Task"), "events": s.get("events", []), "has_secret": bool(s.get("secret")), "enabled": bool(s.get("enabled"))}


def save(data_dir, valori: dict) -> dict:
    s = dict(governance.load_settings(data_dir).get("tickets") or {})
    if "kind" in valori:
        if valori["kind"] not in KINDS:
            raise ValueError("Ticketing: jira, servicenow, glpi or generic.")
        s["kind"] = valori["kind"]
    if "url" in valori:
        if valori["url"] and not re.fullmatch(r"https://[^\s]{4,300}", valori["url"]):
            raise ValueError("The address of the ticketing service is https://…")
        s["url"] = valori["url"].rstrip("/")
    for k, m in (("user", 120), ("project", 40), ("issue_type", 40)):
        if k in valori:
            s[k] = str(valori[k] or "")[:m]
    if "events" in valori:
        if not isinstance(valori["events"], list) or any(e not in notify.EVENTS for e in valori["events"]):
            raise ValueError("Unknown alert.")
        s["events"] = valori["events"]
    if "enabled" in valori:
        s["enabled"] = bool(valori["enabled"])
    if valori.get("secret"):
        s["secret"] = notify.protect(valori["secret"])
    governance.save_settings(data_dir, "tickets", s)
    return settings(data_dir)


def request_for(s: dict, segreto: str, titolo: str, testo: str) -> urllib.request.Request:
    tipo = s["kind"]
    intestazioni = {"Content-Type": "application/json", "Accept": "application/json"}
    if tipo == "jira":
        url = s["url"] + "/rest/api/2/issue"
        corpo = {"fields": {"project": {"key": s["project"]}, "summary": titolo[:250], "description": testo[:30000], "issuetype": {"name": s["issue_type"] or "Task"}}}
        intestazioni["Authorization"] = "Basic " + base64.b64encode(f"{s['user']}:{segreto}".encode()).decode()
    elif tipo == "servicenow":
        url = s["url"] + "/api/now/table/incident"
        corpo = {"short_description": titolo[:160], "description": testo[:4000], "category": "software", "caller_id": s["user"]}
        intestazioni["Authorization"] = "Basic " + base64.b64encode(f"{s['user']}:{segreto}".encode()).decode()
    elif tipo == "glpi":
        url = s["url"] + "/apirest.php/Ticket"
        corpo = {"input": {"name": titolo[:250], "content": testo[:30000], "type": 1, "urgency": 3}}
        intestazioni["App-Token"] = s["project"]
        intestazioni["Authorization"] = "user_token " + segreto
    else:
        url = s["url"]
        corpo = {"title": titolo, "text": testo, "source": "Windows Maintenance Manager"}
        if segreto:
            intestazioni["Authorization"] = "Bearer " + segreto
    return urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), headers=intestazioni, method="POST")


def ticket_id(tipo: str, risposta: dict) -> str:
    if tipo == "jira":
        return str(risposta.get("key", ""))
    if tipo == "servicenow":
        return str((risposta.get("result") or {}).get("number", ""))
    if tipo == "glpi":
        return str(risposta.get("id", ""))
    return str(risposta.get("id") or risposta.get("key") or risposta.get("number") or "")


def create(data_dir, titolo: str, testo: str, opener=None) -> dict:
    """Opens a ticket; returns {"ok", "id" or "error"}."""
    from . import appsettings
    s = settings(data_dir)
    if not s["kind"] or not s["url"]:
        return {"ok": False, "error": "ticketing is not set up"}
    if not appsettings.allowed(data_dir, "webhook"):
        return {"ok": False, "error": "outgoing connections are off"}
    grezzo = governance.load_settings(data_dir).get("tickets", {}).get("secret", "")
    segreto = notify.unprotect(grezzo) if grezzo else ""
    try:
        with (opener or urllib.request.urlopen)(request_for(s, segreto, titolo, testo), timeout=20) as r:
            risposta = json.loads(r.read(256 * 1024).decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(getattr(e, "reason", e))[:200]}
    return {"ok": True, "id": ticket_id(s["kind"], risposta if isinstance(risposta, dict) else {})}


def for_event(data_dir, evento: str) -> bool:
    s = settings(data_dir)
    return s["enabled"] and evento in s["events"]


def version_note() -> Optional[str]:
    return None
