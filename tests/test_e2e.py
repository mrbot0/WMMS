"""Browser test of the console: every page in headless Chromium against an agent in preview mode with test data.
Needs Node.js and Playwright (npm i -g playwright && npx playwright install chromium, or WMM_PLAYWRIGHT=<node_modules>);
without them the test is skipped, so the suite still runs on any PC."""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests import test_api, test_apps
from wmm.agent import apps

SCRIPT = Path(__file__).parent / "e2e" / "console_check.js"
I18N_SCRIPT = Path(__file__).parent / "e2e" / "i18n_check.js"
FLOWS_SCRIPT = Path(__file__).parent / "e2e" / "flows_check.js"
I18N_BASELINE = Path(__file__).parent / "e2e" / "i18n_baseline.json"


def playwright_modules():
    """The node_modules folder that holds Playwright: WMM_PLAYWRIGHT, the global npm folder or the npx cache."""
    candidati = [os.environ.get("WMM_PLAYWRIGHT", "")]
    npm = shutil.which("npm")
    if npm:
        try:
            candidati.append(subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=20).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    candidati += sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\npm-cache\_npx\*\node_modules")))
    for cartella in candidati:
        if cartella and (Path(cartella) / "playwright" / "package.json").exists() and browser_installed(Path(cartella)):
            return cartella
    return None


def browser_installed(cartella: Path) -> bool:
    """Every Playwright version needs its own Chromium build: use a copy whose build is already downloaded."""
    try:
        browsers = json.loads((cartella / "playwright-core" / "browsers.json").read_text(encoding="utf-8"))["browsers"]
    except (OSError, ValueError, KeyError):
        return False
    radice = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"))
    for voce in browsers:
        if voce.get("name") == "chromium-headless-shell":
            return (radice / f"chromium_headless_shell-{voce.get('revision')}").is_dir()
    return False


MODULES = playwright_modules() if shutil.which("node") else None
_SOURCE = None


def from_the_app(testo: str) -> bool:
    """Text written by the app (in its JavaScript or Python), not data of this PC such as the description of a Windows
    service or the name of a program: those stay as Windows or their makers wrote them."""
    global _SOURCE
    if _SOURCE is None:
        radice = Path(__file__).resolve().parent.parent / "wmm"
        _SOURCE = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in list(radice.rglob("*.js")) + list(radice.rglob("*.py"))
                            if "i18n_" not in f.name)
    pezzi = [p.strip() for p in re.split(r"[\d%°·:()\[\]/]+", testo) if len(p.strip()) >= 10 and " " in p.strip()]
    return any(p in _SOURCE for p in pezzi)


SAMPLE = [test_apps.app("VLC media player", "3.0.18", installed="2023-01-01"), test_apps.app("Some Game", last_used="2026-10-30"),
          test_apps.app("OneLaunch"), test_apps.app("TeamViewer")]


@unittest.skipUnless(MODULES, "Node.js with Playwright is not installed")
class Console(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    admin = True

    def test_every_page_loads_without_errors(self):
        self.agent.preview = True  # nothing the pages do can change this PC
        dati = {"apps": SAMPLE, "store": [], "browsers": [{"id": "chrome", "name": "Google Chrome", "cache_mb": 900.0, "files": 10, "running": False}],
                "installers": {"files": [], "count": 0, "mb": 0, "folder": "C:\\Users\\x\\Downloads"}, "errors": [], "winget": True,
                "usage_source": "test", "scanned": "2026-11-03T10:00:00", "rules": apps.RULES_INFO}
        dati["suggestions"] = apps.suggestions(SAMPLE, [], dati["browsers"])
        rete = {"adapters": [], "targets": [], "errors": []}  # the shared fixture refuses network scans on purpose
        with mock.patch.object(apps, "scan", return_value=dati), mock.patch.object(test_api.inventory, "collect_network", return_value=rete):
            risultato = subprocess.run(["node", str(SCRIPT), f"http://127.0.0.1:{self.port}", self.agent.token], capture_output=True, text=True,
                                       encoding="utf-8", errors="replace", timeout=600, env=dict(os.environ, NODE_PATH=MODULES))
        try:
            esito = json.loads(risultato.stdout or "{}")
        except ValueError:
            self.fail(f"no result from the browser check: {risultato.stdout[-500:]} {risultato.stderr[-500:]}")
        self.assertEqual(esito.get("failures"), [], json.dumps(esito, indent=1))
        self.assertGreaterEqual(esito.get("pages", 0), 27)

    def test_critical_flows(self):
        """2.11: sign-in, what a role sees, a run that needs approval, the decision, users and clients (accounts on)."""
        from wmm.agent import accounts as A, actions as azioni, appsettings
        self.agent.preview = True
        conti = self.agent.accounts
        conti.setup("admin", "Adm1n!Flows2026")
        conti.create_user({"username": "vera", "role_id": "viewer", "password": "V1ewer!Flows2026"})
        # Help desk: sees every page and may run every tool, but not without a second person (no approvals.bypass).
        ruolo = conti.create_role({"name": "Help desk", "permissions": sorted(p for p in A.ALL if p.startswith(("run.", "view.")))})
        conti.create_user({"username": "luca", "role_id": ruolo["id"], "password": "H3lpdesk!Flows2026"})
        appsettings.save(self.agent.data_dir, {"approval_levels": ["moderate", "high"]})
        strumento = next(a.id for a in azioni.CATALOG.values() if a.risk == "moderate" and a.kind != "report" and not a.id.startswith("custom."))
        self.agent._central_server.save_tenant({"name": "Rossi Impianti"})
        dati = {"admin": ["admin", "Adm1n!Flows2026"], "viewer": ["vera", "V1ewer!Flows2026"], "helpdesk": ["luca", "H3lpdesk!Flows2026"],
                "tool": strumento, "tenant": "Rossi Impianti"}
        risultato = subprocess.run(["node", str(FLOWS_SCRIPT), f"http://127.0.0.1:{self.port}", self.agent.token, json.dumps(dati)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=600, env=dict(os.environ, NODE_PATH=MODULES))
        try:
            esito = json.loads(risultato.stdout or "{}")
        except ValueError:
            self.fail(f"no result from the flows check: {risultato.stdout[-500:]} {risultato.stderr[-500:]}")
        self.assertEqual(esito.get("failures"), [], json.dumps(esito, indent=1))
        self.assertGreaterEqual(esito.get("steps", 0), 9)

    def test_italian_is_complete(self):
        """2.11: every page and tab in Italian; English sentences on screen must be in the baseline (which only shrinks)."""
        self.agent.preview = True
        rete = {"adapters": [], "targets": [], "errors": []}
        with mock.patch.object(test_api.inventory, "collect_network", return_value=rete):
            risultato = subprocess.run(["node", str(I18N_SCRIPT), f"http://127.0.0.1:{self.port}", self.agent.token], capture_output=True, text=True,
                                       encoding="utf-8", errors="replace", timeout=900, env=dict(os.environ, NODE_PATH=MODULES))
        try:
            esito = json.loads(risultato.stdout or "{}")
        except ValueError:
            self.fail(f"no result from the Italian check: {risultato.stdout[-500:]} {risultato.stderr[-500:]}")
        if os.environ.get("WMM_I18N_REPORT"):
            Path(os.environ["WMM_I18N_REPORT"]).write_text(json.dumps(esito, indent=1, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(esito.get("problems"), [])
        noti = set(json.loads(I18N_BASELINE.read_text(encoding="utf-8"))) if I18N_BASELINE.exists() else set()
        nuovi = [s for s in esito.get("untranslated", []) if s not in noti and from_the_app(s)]
        self.assertEqual(nuovi, [], "English text without Italian: add it to wmm/web/js/i18n_pages.js")


if __name__ == "__main__":
    unittest.main()
