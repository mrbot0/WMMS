"""Browser test of the console: every page in headless Chromium against an agent in preview mode with test data.
Needs Node.js and Playwright (npm i -g playwright && npx playwright install chromium, or WMM_PLAYWRIGHT=<node_modules>);
without them the test is skipped, so the suite still runs on any PC."""
import glob
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests import test_api, test_apps
from wmm.agent import apps

SCRIPT = Path(__file__).parent / "e2e" / "console_check.js"


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


if __name__ == "__main__":
    unittest.main()
