"""OpenAPI 3.1 description of the console API (2.11), built from the route table itself, so it cannot drift from the
code: every route with its method, path parameters (with their pattern), the permissions it needs when accounts are
on and the first line of its docstring. Served at /api/v1/openapi.json for API token users and written to
docs/openapi.json by tools/build_docs.py."""
from __future__ import annotations

import re
from typing import Dict, List

import wmm

GROUP = re.compile(r"\((?!\?)[^)]*\)")
NAMES = {r"(a[0-9a-f]{16})": "agent_id", r"([0-9a-f]{32})": "run_id", r"(\d+)": "id", r"(\d{1,9})": "id", r"(\d{1,10})": "id",
         r"(k[0-9a-f]{10})": "tenant_id", r"(c[0-9a-f]{10})": "catalog_id", r"(r[0-9a-f]{10})": "ring_id", r"(t[0-9a-f]{12})": "token_id",
         r"(u[0-9a-f]{12})": "user_id", r"([0-9a-f]{12})": "batch", r"([0-9a-f]{8})": "script_id"}
WRITE = ("POST", "PUT", "PATCH", "DELETE")


def _path(schema: str) -> tuple:
    """/api/v1/central/agents/(a[0-9a-f]{16}) -> /api/v1/central/agents/{agent_id} and its parameters."""
    parametri: List[dict] = []
    usati: Dict[str, int] = {}

    def nome(m) -> str:
        g = m.group(0)
        base = NAMES.get(g) or ("area" if "cleanup|" in g else "action" if re.fullmatch(r"\([a-z\-|]+\)", g) else "name")
        usati[base] = usati.get(base, 0) + 1
        n = base if usati[base] == 1 else f"{base}{usati[base]}"
        parametri.append({"name": n, "in": "path", "required": True, "schema": {"type": "string", "pattern": "^" + m.group(0)[1:-1] + "$"}})
        return "{" + n + "}"
    return GROUP.sub(nome, schema).replace("\\", ""), parametri


def build(routes, required, public) -> dict:
    percorsi: Dict[str, dict] = {}
    for metodo, schema, funzione in routes:
        if metodo == "HEAD":
            continue
        percorso, parametri = _path(schema.pattern)
        nome = funzione.__name__
        doc = (funzione.__doc__ or "").strip().splitlines()
        permessi = [] if nome in public else required(nome, metodo, ("cleanup", "x", "run"))
        voce = {"operationId": nome, "summary": doc[0] if doc else nome.replace("_", " ").capitalize(),
                "tags": [percorso.split("/")[3] if len(percorso.split("/")) > 3 else "agent"],
                "x-permissions": permessi,
                "responses": {"200": {"description": "OK", "content": {"application/json": {}}},
                              "401": {"description": "Sign in (accounts on) or a valid token is needed"},
                              "403": {"description": "The role lacks a permission listed in x-permissions"}}}
        if parametri:
            voce["parameters"] = parametri
        if metodo in WRITE and metodo != "DELETE":
            voce["requestBody"] = {"required": False, "content": {"application/json": {"schema": {"type": "object"}}}}
        if nome in public:
            voce["security"] = []
        percorsi.setdefault(percorso, {})[metodo.lower()] = voce
    return {
        "openapi": "3.1.0",
        "info": {"title": "Windows Maintenance Manager API", "version": wmm.VERSION,
                 "description": "The API of the console. Every write needs the X-WMM-Token header of the console or, with accounts on, an API token "
                                "(Settings › API tokens) sent as Authorization: Bearer wmm_…. With accounts on, x-permissions lists what the "
                                "role of the user (or the scopes of the token) must include. Runs of tools are also checked tool by tool."},
        "servers": [{"url": "http://127.0.0.1:8765", "description": "the console on this PC"}],
        "components": {"securitySchemes": {
            "token": {"type": "http", "scheme": "bearer", "description": "API token (wmm_…)"},
            "session": {"type": "apiKey", "in": "header", "name": "X-WMM-Session", "description": "session of a signed-in user"}}},
        "security": [{"token": []}, {"session": []}],
        "paths": dict(sorted(percorsi.items())),
    }


def document() -> dict:
    from . import api, permissions
    return build(api.ROUTES, permissions.required, permissions.PUBLIC)
