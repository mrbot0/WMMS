"""The executive report as PDF (2.10): one or two pages for the management or the customer, written here without extra
packages (PDF 1.4, standard Helvetica, WinAnsi text so Italian accents print). Health of the PCs, what was done in
the month and whether it worked, incidents, updates, compliance, the PCs that need attention and warranties that
expire. Built from this PC alone, or from every PC of the central server when this PC is the server."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

A4 = (595, 842)
MARGIN = 50


class Pdf:
    """Just enough PDF: pages with text, lines and filled rectangles."""

    def __init__(self):
        self.pages: List[List[str]] = []
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([])
        self.y = A4[1] - MARGIN

    @staticmethod
    def _esc(t: str) -> str:
        t = t.encode("cp1252", "replace").decode("cp1252")
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def text(self, x: float, y: float, testo: str, size: float = 10, bold: bool = False, color=(0, 0, 0)) -> None:
        r, g, b = color
        self.pages[-1].append(f"BT /{'F2' if bold else 'F1'} {size} Tf {r} {g} {b} rg {x:.1f} {y:.1f} Td ({self._esc(testo)}) Tj ET")

    def rect(self, x: float, y: float, w: float, h: float, color=(0.2, 0.4, 0.8)) -> None:
        r, g, b = color
        self.pages[-1].append(f"{r} {g} {b} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, gray: float = 0.8) -> None:
        self.pages[-1].append(f"{gray} G 0.5 w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def need(self, spazio: float) -> None:
        if self.y - spazio < MARGIN:
            self.new_page()

    def para(self, testo: str, size: float = 10, bold: bool = False, color=(0, 0, 0), larghezza: int = 95) -> None:
        parole, riga = testo.split(), ""
        for p in parole:
            if len(riga) + len(p) + 1 > larghezza:
                self.need(size + 4)
                self.text(MARGIN, self.y, riga, size, bold, color)
                self.y -= size + 4
                riga = p
            else:
                riga = (riga + " " + p).strip()
        if riga:
            self.need(size + 4)
            self.text(MARGIN, self.y, riga, size, bold, color)
            self.y -= size + 4

    def bytes(self) -> bytes:
        oggetti: List[bytes] = []

        def add(b: str) -> int:
            oggetti.append(b.encode("latin-1"))
            return len(oggetti)
        catalogo = add("")  # placeholders for 1 and 2
        pagine = add("")
        f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        figli = []
        for comandi in self.pages:
            flusso = "\n".join(comandi).encode("cp1252", "replace")
            contenuto = len(oggetti) + 1
            oggetti.append(f"<< /Length {len(flusso)} >>\nstream\n".encode() + flusso + b"\nendstream")
            figli.append(add(f"<< /Type /Page /Parent {pagine} 0 R /MediaBox [0 0 {A4[0]} {A4[1]}] /Contents {contenuto} 0 R "
                             f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> >>"))
        oggetti[catalogo - 1] = f"<< /Type /Catalog /Pages {pagine} 0 R >>".encode()
        oggetti[pagine - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in figli)}] /Count {len(figli)} >>".encode()
        uscita = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posizioni = []
        for i, o in enumerate(oggetti, 1):
            posizioni.append(len(uscita))
            uscita += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(uscita)
        uscita += f"xref\n0 {len(oggetti) + 1}\n0000000000 65535 f \n".encode()
        for p in posizioni:
            uscita += f"{p:010d} 00000 n \n".encode()
        uscita += f"trailer\n<< /Size {len(oggetti) + 1} /Root {catalogo} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(uscita)


T = {
    "it": {"title": "Rapporto direzionale", "period": "Periodo", "pcs": "PC", "online": "raggiungibili", "health": "Salute media", "attention": "Da seguire",
           "compliance": "Conformità", "areas": "Salute per area", "work": "Interventi del periodo", "runs": "esecuzioni", "fixed": "risolti",
           "not_fixed": "non risolti", "failed": "falliti", "incidents": "Incidenti", "open": "aperti", "closed": "chiusi", "updates": "Aggiornamenti di Windows",
           "pending": "in attesa", "critical": "critici", "last": "ultimo installato", "risks": "Cosa richiede attenzione", "none": "Nulla da segnalare.",
           "warranty": "Garanzie in scadenza entro 90 giorni", "footer": "Generato da Windows Maintenance Manager", "weak": "salute sotto 60",
           "days": "giorni fa"},
    "en": {"title": "Executive report", "period": "Period", "pcs": "PCs", "online": "reachable", "health": "Average health", "attention": "Need attention",
           "compliance": "Compliance", "areas": "Health by area", "work": "Work in the period", "runs": "runs", "fixed": "fixed", "not_fixed": "not fixed",
           "failed": "failed", "incidents": "Incidents", "open": "open", "closed": "closed", "updates": "Windows updates", "pending": "pending",
           "critical": "critical", "last": "last installed", "risks": "What needs attention", "none": "Nothing to report.",
           "warranty": "Warranties expiring within 90 days", "footer": "Generated by Windows Maintenance Manager", "weak": "health under 60", "days": "days ago"},
}


def _colore(v: Optional[float]) -> Tuple[float, float, float]:
    if v is None:
        return (0.7, 0.7, 0.7)
    return (0.18, 0.6, 0.35) if v >= 80 else (0.85, 0.6, 0.15) if v >= 60 else (0.8, 0.25, 0.25)


def build(dati: dict, lang: str = "it") -> bytes:
    t = T.get(lang, T["it"])
    pdf = Pdf()
    pdf.rect(0, A4[1] - 90, A4[0], 90, (0.12, 0.2, 0.35))
    pdf.text(MARGIN, A4[1] - 45, dati.get("org") or "Windows Maintenance Manager", 20, True, (1, 1, 1))
    pdf.text(MARGIN, A4[1] - 68, f"{t['title']} · {t['period']} {dati['start'][:10]} – {dati['end'][:10]}", 11, False, (0.85, 0.9, 1))
    pdf.y = A4[1] - 120
    kpi = [(t["pcs"], str(dati["pcs"]), f"{dati['online']} {t['online']}"), (t["health"], "—" if dati["overall"] is None else str(dati["overall"]), "/100"),
           (t["attention"], str(dati["weak"]), t["weak"]), (t["compliance"], "—" if dati["compliance"] is None else f"{dati['compliance']}%", "")]
    larghezza = (A4[0] - 2 * MARGIN) / 4
    for i, (k, v, sub) in enumerate(kpi):
        x = MARGIN + i * larghezza
        pdf.text(x, pdf.y, k.upper(), 8, True, (0.4, 0.4, 0.45))
        pdf.text(x, pdf.y - 26, v, 22, True)
        pdf.text(x, pdf.y - 40, sub, 8, False, (0.4, 0.4, 0.45))
    pdf.y -= 70
    pdf.line(MARGIN, pdf.y, A4[0] - MARGIN, pdf.y)
    pdf.y -= 22
    pdf.text(MARGIN, pdf.y, t["areas"], 13, True)
    pdf.y -= 18
    for nome, valore in dati["areas"]:
        pdf.need(16)
        pdf.text(MARGIN, pdf.y, nome, 9)
        pdf.rect(MARGIN + 150, pdf.y - 2, 300, 9, (0.92, 0.93, 0.95))
        if valore is not None:
            pdf.rect(MARGIN + 150, pdf.y - 2, 3 * valore, 9, _colore(valore))
        pdf.text(MARGIN + 460, pdf.y, "—" if valore is None else str(valore), 9, True)
        pdf.y -= 15
    pdf.y -= 10
    r = dati["runs"]
    for titolo, righe in ((t["work"], [f"{r['total']} {t['runs']} · {r['fixed']} {t['fixed']} · {r['not_fixed']} {t['not_fixed']} · {r['failed']} {t['failed']}"]),
                          (t["incidents"], [f"{dati['incidents']['open']} {t['open']} · {dati['incidents']['closed']} {t['closed']}"]),
                          (t["updates"], [f"{dati['updates']['pending']} {t['pending']} · {dati['updates']['critical']} {t['critical']}" +
                                          (f" · {t['last']} {dati['updates']['days']} {t['days']}" if dati['updates'].get('days') is not None else "")])):
        pdf.need(40)
        pdf.text(MARGIN, pdf.y, titolo, 13, True)
        pdf.y -= 17
        for riga in righe:
            pdf.para(riga, 10)
        pdf.y -= 6
    pdf.need(40)
    pdf.text(MARGIN, pdf.y, t["risks"], 13, True)
    pdf.y -= 17
    for riga in dati["risks"] or [t["none"]]:
        pdf.para("• " + riga, 10)
    if dati.get("warranty"):
        pdf.y -= 6
        pdf.need(40)
        pdf.text(MARGIN, pdf.y, t["warranty"], 13, True)
        pdf.y -= 17
        for riga in dati["warranty"]:
            pdf.para("• " + riga, 10)
    for i, pagina in enumerate(pdf.pages):
        pagina.append(f"BT /F1 8 Tf 0.5 0.5 0.5 rg {MARGIN} 25 Td ({Pdf._esc(t['footer'] + ' · ' + dati['end'][:10] + f' · {i + 1}/{len(pdf.pages)}')}) Tj ET")
    return pdf.bytes()


def collect(data_dir: Path, store=None, machine_id: str = "", central_server=None, org: str = "", lang: str = "it", days: int = 30) -> dict:
    """The figures of the report: the central server's PCs when there are any, else this PC."""
    from . import actions, advisor, digest, incidents
    nomi = {**digest.AREA_NAMES.get(lang, digest.AREA_NAMES["en"])}
    adesso = datetime.now()
    inizio = adesso - timedelta(days=days)
    agenti = central_server.agents() if central_server is not None else []
    if agenti:
        punteggi = [a["overall"] for a in agenti if a["overall"] is not None]
        aree = {}
        for a in agenti:
            for k, v in (central_server.agent(a["id"])["summary"].get("scores") or {}).items():
                if v is not None:
                    aree.setdefault(k, []).append(v)
        rischi = [f"{a['hostname']}: {a['overall']}/100" for a in agenti if (a["overall"] or 100) < 60]
        rischi += [f"{a['hostname']}: {a['compliance']}%" for a in agenti if a["compliance"] is not None and a["compliance"] < 80]
        garanzie = [f"{a['hostname']} ({a['asset_tag'] or '—'}): {a['warranty_until']}" for a in agenti
                    if a["warranty_until"] and a["warranty_until"] <= (adesso + timedelta(days=90)).date().isoformat()]
        conf = [a["compliance"] for a in agenti if a["compliance"] is not None]
        base = {"pcs": len(agenti), "online": sum(a["online"] for a in agenti), "overall": round(sum(punteggi) / len(punteggi)) if punteggi else None,
                "weak": sum(1 for a in agenti if (a["overall"] or 100) < 60), "compliance": round(sum(conf) / len(conf), 1) if conf else None,
                "areas": [(nomi.get(k, k), round(sum(v) / len(v))) for k, v in sorted(aree.items())], "risks": rischi[:20], "warranty": garanzie[:20]}
    else:
        dati = digest.collect(data_dir, store, machine_id, now=adesso, events={"bsod": [], "warning": {"signals": [], "forecasts": []}})
        from . import baselines
        conf = baselines.last_summary(data_dir).get("percent")
        base = {"pcs": 1, "online": 1, "overall": dati["overall"], "weak": 1 if (dati["overall"] or 100) < 60 else 0, "compliance": conf,
                "areas": [(nomi.get(k, k), dati["scores"].get(k)) for k in actions.AREAS], "risks": [], "warranty": []}
        base["risks"] = [f"{nomi.get(k, k)}: {v}/100" for k, v in dati["scores"].items() if v is not None and v < 60]
    corse = [r for r in (store.runs(machine_id, limit=5000) if store is not None else []) if (r.get("started") or "") >= inizio.isoformat()]
    verdetti = [r.get("verify") for r in corse if isinstance(r.get("verify"), dict)]
    inc = incidents.listing(data_dir)
    inc = [i for i in inc if i["at"] >= inizio.isoformat()]
    try:
        from . import updatepolicy
        u = updatepolicy.compliance() if central_server is None else {"pending": [], "critical": 0, "days_since_last": None}
    except Exception:  # noqa: BLE001
        u = {"pending": [], "critical": 0, "days_since_last": None}
    return dict(base, org=org, start=inizio.isoformat(timespec="seconds"), end=adesso.isoformat(timespec="seconds"),
                runs={"total": len(corse), "fixed": sum(1 for v in verdetti if v.get("verdict") in ("fixed", "applied", "freed")),
                      "not_fixed": sum(1 for v in verdetti if v.get("verdict") in ("not_fixed", "worse", "nothing_freed")),
                      "failed": sum(1 for r in corse if r["status"] == "error")},
                incidents={"open": sum(1 for i in inc if i["status"] != "closed"), "closed": sum(1 for i in inc if i["status"] == "closed")},
                updates={"pending": len(u.get("pending", [])), "critical": u.get("critical", 0), "days": u.get("days_since_last")},
                overall_check=advisor.overall_score({}) if False else None)
