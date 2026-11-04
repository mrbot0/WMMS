"""Guided diagnosis. Search by symptom proposes reports and fixes; this goes one step further and decides which
fixes are really needed: for every fix of the symptom that has a before/after check (wmm/agent/verify.py) the check is
read now, in read-only mode, and the fix is recommended only when the state is not healthy. Fixes without a check stay
as "try if the others do not help". Nothing is changed: the user still chooses what to run."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Dict, Optional

from . import actions, symptoms, verify

STATES = ("needed", "fine", "unknown", "manual")


def diagnose(symptom_id: str, runner: Optional[Callable[[str], str]] = None, catalog: Optional[dict] = None) -> dict:
    catalogo = catalog if catalog is not None else actions.CATALOG
    sintomo = next((s for s in symptoms.SYMPTOMS if s.id == symptom_id), None)
    if sintomo is None:
        raise KeyError(symptom_id)
    correzioni = [a for a in sintomo.steps if a in catalogo and catalogo[a].kind != "report"]
    script = sorted({verify.CHECKS[a].script for a in correzioni if a in verify.CHECKS})
    # The same check (for example the internet one) is read once, and the reads run side by side.
    letture: Dict[str, Optional[str]] = {}
    if script:
        with ThreadPoolExecutor(max_workers=min(4, len(script)), thread_name_prefix="wmm-diagnose") as pool:
            for testo, valore in zip(script, pool.map(lambda t: verify.read(verify.Check("", t), runner), script)):
                letture[testo] = valore
    passi = []
    for action_id in correzioni:
        controllo = verify.CHECKS.get(action_id)
        if controllo is None:
            passi.append({"action_id": action_id, "state": "manual", "label": "", "reading": None})
            continue
        lettura = letture.get(controllo.script)
        if lettura is None or controllo.ok is None:
            stato = "unknown"
        else:
            stato = "fine" if controllo.ok(lettura) else "needed"
        passi.append({"action_id": action_id, "state": stato, "label": controllo.label, "reading": lettura})
    necessari = [p["action_id"] for p in passi if p["state"] == "needed"]
    manuali = [p["action_id"] for p in passi if p["state"] == "manual"]
    if necessari:
        nota = f"{len(necessari)} fixes match what this PC shows now: run them in this order."
    elif manuali:
        nota = "The checked settings are fine: the cause is elsewhere. Read the reports, then try the remaining fixes."
    else:
        nota = "Everything this diagnosis can check is fine on this PC."
    return {"symptom": symptom_id, "title": sintomo.title, "title_it": sintomo.title_it, "checked": datetime.now().isoformat(timespec="seconds"),
            "reports": [a for a in sintomo.steps if a in catalogo and catalogo[a].kind == "report"],
            "steps": passi, "recommended": necessari, "note": nota}
