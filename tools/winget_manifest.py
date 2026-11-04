"""The winget manifests of a release (schema 1.6: version, installer and default locale files), so that
"winget install mrbot0.WindowsMaintenanceManager" and "winget upgrade" work on every PC of a fleet.

    python tools/winget_manifest.py --version 2.6.0 --url <setup URL> --sha256 <hash> [--out release/winget]

The folder it writes follows the winget-pkgs layout (manifests/m/mrbot0/WindowsMaintenanceManager/<version>): submit it
with "wingetcreate submit <folder>" or a pull request to microsoft/winget-pkgs. Check the license line before the first
submission: the repository has no LICENSE file yet."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict

PACKAGE_ID = "mrbot0.WindowsMaintenanceManager"
PUBLISHER = "mrbot0"
NAME = "Windows Maintenance Manager"
REPO = "https://github.com/mrbot0/WMMS"
SCHEMA = "1.6.0"
LICENSE = "Proprietary"


def _quote(testo: str) -> str:
    return "'" + str(testo).replace("'", "''") + "'"


def manifests(version: str, url: str, sha256: str, license_name: str = LICENSE) -> Dict[str, str]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("The version must look like 2.6.0")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise ValueError("The SHA256 must be 64 hex characters")
    if not url.startswith("https://"):
        raise ValueError("winget only accepts https installer URLs")

    def intestazione(tipo: str) -> str:
        return f"# Created by tools/winget_manifest.py\n# yaml-language-server: $schema=https://aka.ms/winget-manifest.{tipo}.{SCHEMA}.schema.json\n\n"

    comune = f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\n"
    return {
        f"{PACKAGE_ID}.yaml": intestazione("version") + comune +
            f"DefaultLocale: en-US\nManifestType: version\nManifestVersion: {SCHEMA}\n",
        f"{PACKAGE_ID}.installer.yaml": intestazione("installer") + comune +
            "InstallerType: inno\nScope: machine\nUpgradeBehavior: install\nElevationRequirement: elevationRequired\n"
            "MinimumOSVersion: 10.0.17763.0\n"
            "Dependencies:\n  PackageDependencies:\n  - PackageIdentifier: Python.Python.3.12\n"
            "Installers:\n- Architecture: x64\n"
            f"  InstallerUrl: {url}\n  InstallerSha256: {sha256.upper()}\n"
            f"ManifestType: installer\nManifestVersion: {SCHEMA}\n",
        f"{PACKAGE_ID}.locale.en-US.yaml": intestazione("defaultLocale") + comune +
            f"PackageLocale: en-US\nPublisher: {PUBLISHER}\nPublisherUrl: https://github.com/{PUBLISHER}\nPackageName: {NAME}\n"
            f"PackageUrl: {REPO}\nLicense: {_quote(license_name)}\n"
            f"ShortDescription: {_quote('Local maintenance console for Windows: diagnostics, safe fixes, schedules and a network scanner.')}\n"
            "Description: |-\n  A web console that runs on the PC: 350 diagnostics and fixes with restore points, before/after checks and precise undo,\n"
            "  schedules, alerts by e-mail or Telegram, a network, Wi-Fi and Bluetooth scanner, and fleet summaries.\n"
            "Tags:\n- maintenance\n- cleanup\n- diagnostics\n- network-scanner\n- windows-update\n"
            f"ReleaseNotesUrl: {REPO}/releases/tag/v{version}\n"
            f"ManifestType: defaultLocale\nManifestVersion: {SCHEMA}\n",
    }


def write(out: Path, version: str, url: str, sha256: str, license_name: str = LICENSE) -> Path:
    cartella = Path(out) / "manifests" / PUBLISHER[0].lower() / PUBLISHER / "WindowsMaintenanceManager" / version
    cartella.mkdir(parents=True, exist_ok=True)
    for nome, testo in manifests(version, url, sha256, license_name).items():
        (cartella / nome).write_text(testo, encoding="utf-8", newline="\n")
    return cartella


def main(argomenti=None) -> int:
    parser = argparse.ArgumentParser(description="Write the winget manifests of a release")
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--license", default=LICENSE)
    parser.add_argument("--out", default="release/winget")
    opzioni = parser.parse_args(argomenti)
    try:
        print(write(Path(opzioni.out), opzioni.version, opzioni.url, opzioni.sha256, opzioni.license))
    except ValueError as errore:
        print(errore, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
