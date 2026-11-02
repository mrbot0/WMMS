"""Routines: a group of actions run together on a schedule, at startup or at sign-in.

A schedule stores what it runs in `action_id`: an action id, `routine:<id>` for a routine below
or `playbook:<id>` for a playbook.
"""
from __future__ import annotations

from typing import List, Optional

from . import actions

ROUTINE_PREFIX = "routine:"
PLAYBOOK_PREFIX = "playbook:"

# "suggested" is the frequency proposed when the routine is applied; every field can be changed.
ROUTINES = (
    {"id": "startup_refresh", "title": "Fresh start", "group": "At startup",
     "description": "A few minutes after Windows starts: temporary files, DNS cache and antivirus signatures.",
     "actions": ["cleanup.temp", "network.flush_dns", "security.update_signatures"],
     "suggested": {"kind": "startup", "delay": 5}},
    {"id": "startup_network", "title": "Network ready at startup", "group": "At startup",
     "description": "Clears the DNS and NetBIOS caches at every start, for PCs that move between networks.",
     "actions": ["network.flush_dns", "network.purge_netbios"],
     "suggested": {"kind": "startup", "delay": 2}},
    {"id": "logon_light", "title": "Light sign-in cleanup", "group": "At sign-in",
     "description": "When someone signs in: temporary files and the thumbnail cache, nothing that slows the desktop.",
     "actions": ["cleanup.temp", "storage.thumbnails"],
     "suggested": {"kind": "logon", "delay": 10}},
    {"id": "daily_protection", "title": "Daily protection", "group": "Every day",
     "description": "Fresh antivirus signatures and a quick scan every day at lunchtime.",
     "actions": ["security.update_signatures", "security.quick_scan"],
     "suggested": {"kind": "daily", "time": "12:30"}},
    {"id": "daily_tidy", "title": "Daily tidy-up", "group": "Every day",
     "description": "Temporary files, error reports and the Delivery Optimization cache every evening.",
     "actions": ["cleanup.temp", "storage.wer", "storage.delivery_optimization"],
     "suggested": {"kind": "daily", "time": "19:00"}},
    {"id": "weekly_tuneup", "title": "Weekly tune-up", "group": "Every week",
     "description": "The quick tune-up every Friday: caches, TRIM, DNS, signatures and memory.",
     "actions": ["cleanup.temp", "storage.wer", "storage.thumbnails", "storage.delivery_optimization", "integrity.trim",
                 "network.flush_dns", "security.update_signatures", "performance.free_memory"],
     "suggested": {"kind": "weekly", "time": "13:00", "days": "FRI"}},
    {"id": "weekly_drives", "title": "Drive care", "group": "Every week",
     "description": "Online disk check, then TRIM and optimization of every drive, every Wednesday.",
     "actions": ["integrity.disk_scan", "integrity.trim", "storage.optimize_all"],
     "suggested": {"kind": "weekly", "time": "12:00", "days": "WED"}},
    {"id": "weekly_updates", "title": "Weekly updates", "group": "Every week",
     "description": "Looks for Windows updates and updates Store and desktop apps every Tuesday.",
     "actions": ["updates.scan", "updates.store_apps", "updates.winget_upgrade"],
     "suggested": {"kind": "weekly", "time": "12:00", "days": "TUE"}},
    {"id": "weekly_restore_point", "title": "Weekly restore point", "group": "Every week",
     "description": "A restore point every Monday, so there is always a recent one to go back to.",
     "actions": ["security.restore_point"],
     "suggested": {"kind": "weekly", "time": "10:00", "days": "MON"}},
    {"id": "monthly_repair", "title": "Monthly Windows check", "group": "Every month",
     "description": "Repairs the Windows image and system files and removes obsolete components on the 1st of the month.",
     "actions": ["integrity.dism", "integrity.sfc", "cleanup.components", "integrity.wmi_verify"],
     "suggested": {"kind": "monthly", "time": "11:00", "day": 1}},
    {"id": "monthly_deep_clean", "title": "Monthly deep cleanup", "group": "Every month",
     "description": "Browser caches, Windows logs, shader caches and the Recycle Bin on the 15th of the month.",
     "actions": ["cleanup.temp", "storage.browser_cache", "storage.windows_logs", "cleanup.shader_cache", "cleanup.recycle_bin"],
     "suggested": {"kind": "monthly", "time": "12:00", "day": 15}},
    {"id": "monthly_health", "title": "Monthly health report", "group": "Every month",
     "description": "Read-only: disks, reliability, antivirus, devices and pending restarts, kept in History every month.",
     "actions": ["storage.disk_health", "integrity.reliability_report", "security.defender_status", "updates.problem_devices",
                 "updates.pending_reboot"],
     "suggested": {"kind": "monthly", "time": "12:00", "day": 28}},
)
ROUTINE_BY_ID = {r["id"]: r for r in ROUTINES}
GROUPS = ("At startup", "At sign-in", "Every day", "Every week", "Every month")


def _playbook(playbook_id: str) -> Optional[dict]:
    return next((p for p in actions.PLAYBOOKS if p["id"] == playbook_id), None)


def expand(ref: str) -> List[str]:
    """The action ids a schedule runs. KeyError when the routine, playbook or action no longer exists."""
    if ref.startswith(ROUTINE_PREFIX):
        return list(ROUTINE_BY_ID[ref[len(ROUTINE_PREFIX):]]["actions"])
    if ref.startswith(PLAYBOOK_PREFIX):
        voce = _playbook(ref[len(PLAYBOOK_PREFIX):])
        if voce is None:
            raise KeyError(ref)
        return list(voce["actions"])
    if ref not in actions.CATALOG:
        raise KeyError(ref)
    return [ref]


def _highest(rischi: List[str]) -> str:
    return max(rischi, key=actions.RISKS.index) if rischi else "high"


def describe(ref: str) -> dict:
    """Title, risk, area and actions of what a schedule runs, for the console."""
    try:
        ids = expand(ref)
    except KeyError:
        return {"title": ref, "risk": "high", "area": "unknown", "routine": None, "actions": []}
    rischio = _highest([actions.CATALOG[a].risk for a in ids if a in actions.CATALOG])
    if ref.startswith(ROUTINE_PREFIX):
        voce = ROUTINE_BY_ID[ref[len(ROUTINE_PREFIX):]]
        return {"title": voce["title"], "risk": rischio, "area": "routine", "routine": "routine", "actions": ids}
    if ref.startswith(PLAYBOOK_PREFIX):
        voce = _playbook(ref[len(PLAYBOOK_PREFIX):])
        return {"title": voce["title"], "risk": rischio, "area": "routine", "routine": "playbook", "actions": ids}
    azione = actions.CATALOG[ref]
    return {"title": azione.title, "risk": azione.risk, "area": azione.area, "routine": None, "actions": ids}


def _summary(ids: List[str]) -> dict:
    voci = [actions.CATALOG[a] for a in ids if a in actions.CATALOG]
    return {"actions": [{"id": a.id, "title": a.title, "risk": a.risk, "kind": a.kind} for a in voci],
            "risk": _highest([a.risk for a in voci]),
            "minutes": round(sum(a.minutes for a in voci), 1),
            "reports_only": bool(voci) and all(a.kind == "report" for a in voci)}


def catalog() -> dict:
    proposte = [dict({k: v for k, v in r.items() if k != "actions"}, ref=ROUTINE_PREFIX + r["id"], **_summary(r["actions"]))
                for r in ROUTINES]
    playbook = [{"id": p["id"], "ref": PLAYBOOK_PREFIX + p["id"], "title": p["title"], "description": p["description"],
                 **_summary(p["actions"])} for p in actions.PLAYBOOKS]
    return {"routines": proposte, "playbooks": playbook, "groups": list(GROUPS)}
