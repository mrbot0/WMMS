"""Sign-in with the company accounts (2.10): Microsoft Entra ID or any OpenID Connect provider, and Windows or
Active Directory accounts.

OpenID Connect: authorization code with PKCE (no client secret needed: register the console as a "public client"
with the redirect address http://127.0.0.1:<port>/api/v1/auth/oidc/callback). The code is exchanged directly with
the token endpoint over HTTPS, so the ID token is trusted through TLS as OpenID Connect Core 3.1.3.7 allows; the
issuer, audience, expiry and nonce are still checked. The role comes from a claim (groups or app roles) through a
mapping; unknown people are refused unless a default role is set.

Windows: the password is checked by Windows itself (LogonUserW, network logon) for a local or domain account; the
role comes from the Windows groups of the account through a mapping. Passwords are never stored."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

from . import governance, notify

PENDING_SECONDS = 600
_PENDING: Dict[str, dict] = {}
_LOCK = threading.Lock()


class SsoError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------- settings ----------

DEFAULTS = {"oidc_enabled": False, "issuer": "", "client_id": "", "scopes": "openid profile email", "role_claim": "groups",
            "role_map": {}, "default_role": "", "auto_create": True, "domains": "",
            "windows_enabled": False, "windows_role_map": {}, "windows_default_role": ""}


def settings(data_dir) -> dict:
    s = governance.load_settings(data_dir).get("sso") or {}
    v = {k: s.get(k, d) for k, d in DEFAULTS.items()}
    v["has_secret"] = bool(s.get("client_secret"))
    return v


def save(data_dir, valori: dict, ruoli: List[str]) -> dict:
    attuali = governance.load_settings(data_dir).get("sso") or {}
    nuovi = dict(attuali)
    for k, d in DEFAULTS.items():
        if k not in valori:
            continue
        v = valori[k]
        if isinstance(d, bool):
            if not isinstance(v, bool):
                raise SsoError(f"{k}: true or false.")
        elif isinstance(d, dict):
            if not isinstance(v, dict) or any(not isinstance(a, str) or r not in ruoli for a, r in v.items()):
                raise SsoError("Role mapping: a name and an existing role for each line.")
        elif k in ("default_role", "windows_default_role"):
            if v and v not in ruoli:
                raise SsoError("Unknown role.")
        elif k == "issuer":
            if v and not re.fullmatch(r"https://[^\s]{8,300}", str(v)):
                raise SsoError("The issuer is an https:// address (for Entra ID: https://login.microsoftonline.com/<tenant>/v2.0).")
            if v and re.search(r"/(common|organizations|consumers)(/|$)", str(v)):
                raise SsoError("Use the issuer of your tenant (https://login.microsoftonline.com/<tenant ID>/v2.0), not common or organizations.")
        elif k == "client_id":
            if v and not re.fullmatch(r"[\w.\-]{4,200}", str(v)):
                raise SsoError("The client ID is the application (client) ID of the registration.")
        elif not isinstance(v, str) or len(v) > 300:
            raise SsoError(f"{k}: text.")
        nuovi[k] = v.strip().rstrip("/") if k == "issuer" and isinstance(v, str) else v
    if "client_secret" in valori:
        nuovi["client_secret"] = notify.protect(valori["client_secret"]) if valori["client_secret"] else ""
    governance.save_settings(data_dir, "sso", nuovi)
    return settings(data_dir)


# ---------- OpenID Connect ----------

def _b64url(dati: bytes) -> str:
    return base64.urlsafe_b64encode(dati).rstrip(b"=").decode("ascii")


def _get_json(url: str, opener=None) -> dict:
    with (opener or urllib.request.urlopen)(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=15) as r:
        return json.loads(r.read(512 * 1024).decode("utf-8"))


def discovery(issuer: str, fetch: Optional[Callable[[str], dict]] = None) -> dict:
    dati = (fetch or _get_json)(issuer.rstrip("/") + "/.well-known/openid-configuration")
    for k in ("authorization_endpoint", "token_endpoint"):
        if not str(dati.get(k, "")).startswith("https://"):
            raise SsoError("The provider configuration is not valid.", 502)
    return dati


def start(data_dir, redirect_uri: str, fetch=None) -> str:
    """The address of the provider's sign-in page, with a one-time state, nonce and PKCE verifier kept here."""
    s = settings(data_dir)
    if not s["oidc_enabled"] or not s["issuer"] or not s["client_id"]:
        raise SsoError("Company sign-in is not set up.", 409)
    conf = discovery(s["issuer"], fetch)
    stato, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    with _LOCK:
        for k in [k for k, v in _PENDING.items() if time.time() - v["t"] > PENDING_SECONDS]:
            del _PENDING[k]
        _PENDING[stato] = {"t": time.time(), "nonce": nonce, "verifier": verifier, "redirect": redirect_uri, "token_endpoint": conf["token_endpoint"]}
    parametri = {"client_id": s["client_id"], "response_type": "code", "redirect_uri": redirect_uri, "scope": s["scopes"], "state": stato,
                 "nonce": nonce, "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
                 "response_mode": "query", "prompt": "select_account"}
    return conf["authorization_endpoint"] + "?" + urllib.parse.urlencode(parametri)


def _post_form(url: str, campi: dict, opener=None) -> dict:
    richiesta = urllib.request.Request(url, data=urllib.parse.urlencode(campi).encode(), headers={"Content-Type": "application/x-www-form-urlencoded",
                                                                                                   "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(richiesta, timeout=15) as r:
            return json.loads(r.read(512 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            dettaglio = json.loads(e.read(4096)).get("error_description", "")
        except Exception:  # noqa: BLE001
            dettaglio = ""
        raise SsoError(f"The provider refused the sign-in ({e.code}). {dettaglio[:200]}", 401) from None


def claims(id_token: str) -> dict:
    try:
        parte = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))
    except (IndexError, ValueError):
        raise SsoError("The provider answered with an invalid ID token.", 502) from None


def finish(data_dir, stato: str, code: str, post=None, now: Optional[float] = None) -> dict:
    """Exchanges the code and checks the ID token; returns its claims."""
    with _LOCK:
        attesa = _PENDING.pop(stato or "", None)
    if attesa is None or time.time() - attesa["t"] > PENDING_SECONDS:
        raise SsoError("The sign-in expired or was already used: start again.", 400)
    s = settings(data_dir)
    campi = {"grant_type": "authorization_code", "code": code, "redirect_uri": attesa["redirect"], "client_id": s["client_id"],
             "code_verifier": attesa["verifier"]}
    segreto = governance.load_settings(data_dir).get("sso", {}).get("client_secret")
    if segreto:
        campi["client_secret"] = notify.unprotect(segreto)
    risposta = (post or _post_form)(attesa["token_endpoint"], campi)
    c = claims(str(risposta.get("id_token", "")))
    adesso = now or time.time()
    aud = c.get("aud")
    if c.get("iss", "").rstrip("/") != s["issuer"].rstrip("/"):
        raise SsoError("The ID token comes from another issuer.", 401)
    if s["client_id"] not in (aud if isinstance(aud, list) else [aud]):
        raise SsoError("The ID token is for another application.", 401)
    if float(c.get("exp", 0)) < adesso - 60:
        raise SsoError("The ID token has expired.", 401)
    if c.get("nonce") != attesa["nonce"]:
        raise SsoError("The ID token does not belong to this sign-in.", 401)
    return c


def map_role(valori: List[str], mappa: Dict[str, str], predefinito: str) -> str:
    """The first mapped value wins in the order of the mapping (put the strongest role first)."""
    presenti = {str(v).lower() for v in valori}
    for chiave, ruolo in mappa.items():
        if chiave.lower() in presenti:
            return ruolo
    return predefinito


def oidc_identity(data_dir, c: dict) -> dict:
    s = settings(data_dir)
    nome = str(c.get("preferred_username") or c.get("email") or c.get("upn") or "")
    dominio = nome.split("@")[-1].lower() if "@" in nome else ""
    consentiti = [d.strip().lower() for d in s["domains"].split(",") if d.strip()]
    if consentiti and dominio not in consentiti:
        raise SsoError("This account's domain is not allowed.", 403)
    valori = c.get(s["role_claim"]) or []
    valori = valori if isinstance(valori, list) else [valori]
    return {"subject": "oidc:" + str(c.get("sub") or c.get("oid") or nome), "username": username_from(nome), "display": str(c.get("name") or nome)[:80],
            "email": str(c.get("email") or (nome if "@" in nome else ""))[:200], "role": map_role(valori, s["role_map"], s["default_role"])}


def username_from(nome: str) -> str:
    base = nome.split("@")[0].replace("\\", ".")
    pulito = re.sub(r"[^A-Za-z0-9._-]", ".", base).strip(".-_")[:32]
    return pulito if len(pulito) >= 2 else "user." + hashlib.sha1(nome.encode()).hexdigest()[:8]


# ---------- Windows and Active Directory ----------

def windows_logon(utente: str, password: str) -> Optional[List[str]]:
    """The Windows groups of the account when Windows accepts the password (network logon), else None."""
    import ctypes
    from ctypes import wintypes
    if "\\" in utente:
        dominio, nome = utente.split("\\", 1)
    elif "@" in utente:
        dominio, nome = None, utente
    else:
        dominio, nome = ".", utente
    token = wintypes.HANDLE()
    advapi, kernel = ctypes.windll.advapi32, ctypes.windll.kernel32
    if not advapi.LogonUserW(nome, dominio, password, 3, 0, ctypes.byref(token)):  # LOGON32_LOGON_NETWORK, provider default
        return None
    try:
        necessari = wintypes.DWORD()
        advapi.GetTokenInformation(token, 2, None, 0, ctypes.byref(necessari))  # TokenGroups
        buffer = ctypes.create_string_buffer(necessari.value)
        if not advapi.GetTokenInformation(token, 2, buffer, necessari, ctypes.byref(necessari)):
            return []

        class SidAndAttributes(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]
        conteggio = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD))[0]
        voci = ctypes.cast(ctypes.addressof(buffer) + ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(SidAndAttributes * conteggio)).contents
        gruppi = []
        for voce in voci:
            nome_g, dominio_g = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            n1, n2, uso = wintypes.DWORD(256), wintypes.DWORD(256), wintypes.DWORD()
            if advapi.LookupAccountSidW(None, ctypes.c_void_p(voce.Sid), nome_g, ctypes.byref(n1), dominio_g, ctypes.byref(n2), ctypes.byref(uso)):
                gruppi.append(f"{dominio_g.value}\\{nome_g.value}" if dominio_g.value else nome_g.value)
                gruppi.append(nome_g.value)
        return gruppi
    finally:
        kernel.CloseHandle(token)


def windows_identity(data_dir, utente: str, gruppi: List[str]) -> dict:
    s = settings(data_dir)
    return {"subject": "windows:" + utente.lower(), "username": username_from(utente), "display": utente[:80], "email": "",
            "role": map_role(gruppi, s["windows_role_map"], s["windows_default_role"])}
