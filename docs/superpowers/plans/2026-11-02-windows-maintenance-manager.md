# Windows Maintenance Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suite locale offline con GUI web enterprise in inglese (Dashboard, Cleanup, System Integrity, Services, Schedules, History, Reports) costruita sulla logica di `ottimizza_pc.py`.

**Architecture:** Pacchetto `wmm/` con un agente Python (raccolta dati, punteggi, raccomandazioni, azioni, storico SQLite, pianificazioni via Utilità di pianificazione) esposto da un server HTTP stdlib su `127.0.0.1` con API `/api/v1`. GUI statica HTML/CSS/JS vanilla con grafici SVG; i report HTML autonomi sono generati nel browser riusando gli stessi grafici.

**Tech Stack:** Python 3.9+ solo stdlib (`http.server`, `sqlite3`, `threading`, `json`, `subprocess`), unittest, JS ES2017 senza librerie, SVG.

**Spec:** `docs/superpowers/specs/2026-11-02-windows-maintenance-manager-design.md`

## Global Constraints

- **Lingua: inglese** per GUI, report, export, messaggi API, nuovo codice e chiavi JSON (decisione utente sulla lingua; codice/API in inglese = mia scelta). `ottimizza_pc.py` resta in italiano e viene importato.
- Nessuna dipendenza esterna né CDN: tutto offline.
- Server solo su `127.0.0.1`, porta predefinita `8765`.
- `SERVIZI_PROTETTI` di `ottimizza_pc.py` vincolante.
- Azioni `moderate`/`high`: conferma esplicita (anche quando pianificate) e punto di ripristino prima dell'esecuzione; se fallisce, l'azione non parte. Azioni `safe`: senza conferma, anche in blocco e da pianificazione.
- Ogni azione è pianificabile (once, daily, weekly) nell'Utilità di pianificazione, cartella `\WindowsMaintenanceManager\`; funziona a programma chiuso.
- Ogni record di storico porta `machine_id`.
- `ottimizza_pc.py` e `test_ottimizza_pc.py` invariati e funzionanti.
- Test con `unittest` (stile del progetto). Il progetto non è un repo git: nessun passo di commit.

## Review Focus

1. **Richieste cross-origin verso l'API** (un sito web qualsiasi può fare POST a `127.0.0.1:8765` e lanciare azioni da amministratore) → ogni richiesta non-GET richiede `X-WMM-Token` = token generato all'avvio, e l'header `Host` deve essere `127.0.0.1:<port>` o `localhost:<port>`; altrimenti 403 (Task 6).
2. **Agente senza amministratore** → GUI in sola lettura con banner; le esecuzioni rispondono 409 con messaggio chiaro (Task 6).
3. **PowerShell che restituisce vuoto o JSON non valido** → i collector restituiscono dati parziali con `errors: [...]`, mai eccezioni (Task 3).
4. **Due esecuzioni contemporanee** (doppio clic, pianificazione durante il lavoro) → un solo job di modifica alla volta; il secondo riceve 409 "A run is already in progress" (Task 5, 6).
5. **Task rimosso a mano o cartella spostata** → la pagina Schedules mostra `out_of_sync` e offre "Resync" (Task 7).

---

## File Structure

```
wmm.py                      avvio GUI / esecuzione pianificazione (CLI)
start_wmm.bat               avvio con doppio clic
wmm/__init__.py             VERSION = "1.0.0", APP_NAME = "Windows Maintenance Manager"
wmm/agent/core.py           JobContext, machine_id, is_admin
wmm/agent/actions.py        catalogo Action
wmm/agent/collectors.py     raccolta dati per area
wmm/agent/advisor.py        punteggi e raccomandazioni (puro)
wmm/agent/store.py          SQLite
wmm/agent/jobs.py           esecuzione azioni
wmm/agent/scheduler.py      Utilità di pianificazione (XML task)
wmm/server/api.py           Agent + HTTP server + routing
wmm/web/index.html, css/app.css
wmm/web/js/api.js charts.js ui.js app.js report.js
wmm/web/js/pages/dashboard.js cleanup.js integrity.js services.js schedules.js history.js reports.js
tests/test_actions.py test_store.py test_collectors.py test_advisor.py test_jobs.py test_api.py test_scheduler.py
```

Aree (id): `cleanup`, `integrity`, `services`.

---

### Task 1: Core e catalogo azioni

**Files:** Create `wmm/__init__.py`, `wmm/agent/__init__.py`, `wmm/agent/core.py`, `wmm/agent/actions.py` · Test `tests/__init__.py`, `tests/test_actions.py`

**Interfaces:**
- Consumes da `ottimizza_pc`: `Contesto`, `Esito`, `Stato`, `SequenzaFermata`, `punto_ripristino` e le funzioni `pulizia_file`, `pulizia_componenti`, `svuota_cestino`, `elimina_dump`, `ripara_immagine`, `ripara_file`, `verifica_disco`, `ripara_disco`, `trim`, `servizi_sicuri`, `servizi_xbox`, `servizi_stampa`, `ripristina_servizi`.
- Produces:
  - `core.JobContext(Contesto)`: `__init__(self, log: Callable[[str], None], anteprima: bool = False)`; `scrivi` inoltra a `log` senza codici ANSI; `comando` esegue il processo e manda ogni riga a `log` invece che a `sys.stdout` (stessa decodifica OEM e rimozione `\x00` dell'originale).
  - `core.machine_id() -> str` → `"<HOSTNAME>-<MachineGuid>"` da `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`; fallback solo hostname.
  - `core.is_admin() -> bool`.
  - `core.STATUS = {Stato.OK: "ok", Stato.AVVISO: "warning", Stato.ERRORE: "error", Stato.SALTATO: "skipped", Stato.ANTEPRIMA: "preview"}`.
  - `actions.Action` (dataclass frozen): `id: str, area: str, title: str, description: str, risk: str ("safe"|"moderate"|"high"), minutes: float, run: Callable[[Contesto], Esito], warning: str = ""`; `as_dict()` senza `run`.
  - `actions.CATALOG: Dict[str, Action]`, `actions.by_area(area) -> List[Action]`, `actions.safe(area: Optional[str] = None) -> List[Action]`.

Catalogo (id → risk): `cleanup.temp` safe · `cleanup.components` moderate · `cleanup.recycle_bin` moderate · `cleanup.dumps` moderate · `integrity.disk_scan` safe · `integrity.trim` safe · `integrity.dism` moderate · `integrity.sfc` moderate · `integrity.disk_repair` high · `services.safe` moderate · `services.xbox` high · `services.print` high · `services.restore` moderate. Titoli e warning in inglese (tradurre i testi `conferma=` di `ottimizza_pc.PASSI`).

- [ ] **Step 1: Test** `tests/test_actions.py`: `test_every_action_has_valid_area_and_risk`; `test_non_safe_actions_have_warning` (`warning` non vuoto); `test_safe_cleanup == ["cleanup.temp"]`; `test_job_context_captures_output` (`JobContext(log.append).scrivi("x")` → `["x"]`).
- [ ] **Step 2:** `python -m unittest tests.test_actions -v` → FAIL (modulo assente).
- [ ] **Step 3:** Implementare.
- [ ] **Step 4:** stesso comando → PASS; `python -m unittest test_ottimizza_pc` → PASS.

### Task 2: Storico SQLite

**Files:** Create `wmm/agent/store.py` · Test `tests/test_store.py`

**Interfaces:** `Store(path: Path)` thread-safe (lock + `check_same_thread=False`), date `datetime.now().isoformat(timespec="seconds")`:
- `save_scan(machine_id, area, score: int, data: dict) -> int`; `last_scan(machine_id, area) -> Optional[dict]` (`{id, area, created, score, data}`); `trend(machine_id, area, limit=30) -> List[dict]` (`{created, score}`, crescente).
- `open_run(machine_id, action_id, origin: "manual"|"auto"|"schedule") -> int`; `close_run(run_id, status: str, note: str, bytes_freed: int, log: str) -> None`; `runs(machine_id, area: Optional[str] = None, limit=100) -> List[dict]` (`{id, action_id, area, origin, started, finished, status, note, bytes_freed}`); `run_log(run_id) -> str`; `last_runs_by_action(machine_id) -> Dict[str, dict]`.
- `create_schedule(action_id, kind: "once"|"daily"|"weekly", at: str "YYYY-MM-DDTHH:MM", days: str ("" o "MON,WED"), confirmed: bool) -> int`; `schedules() -> List[dict]`; `schedule(id) -> Optional[dict]`; `update_schedule(id, **fields)`; `delete_schedule(id)`. Campi extra: `enabled`, `last_status`, `last_run`.

- [ ] **Step 1: Test** (`tempfile.TemporaryDirectory`): `test_last_scan_is_most_recent`; `test_trend_ascending`; `test_run_open_and_close` (status `"ok"`, bytes 1024); `test_runs_filtered_by_area`; `test_schedule_crud`.
- [ ] **Step 2:** `python -m unittest tests.test_store -v` → FAIL. **Step 3:** implementare. **Step 4:** → PASS.

### Task 3: Collector per area

**Files:** Create `wmm/agent/collectors.py` · Test `tests/test_collectors.py`

**Interfaces:** Consumes `ottimizza_pc.SCRIPT_CHECKUP`, `CARTELLE_PULIZIA`, `CARTELLE_DUMP`, `GIORNI_FILE_VECCHI`, `file_da_pulire`, `leggi_avvio_servizio`, `servizio_attivo`, `SERVIZI_SICURI|MANUALI|XBOX|STAMPA`, `SERVIZI_PROTETTI`, `leggi_backup`, `come_lista`; `Contesto.powershell_json`. Tutte restituiscono dict serializzabili con `errors: List[str]` sempre presente:
- `collect_system(ctx) -> dict` — output di `SCRIPT_CHECKUP` **rinominato in inglese** con `translate_system(raw: dict) -> dict` (puro): `admin, os{name, build, cpu, board, bios, bios_date, bios_age_days, uptime_hours, startup_items}, memory{free_gb, total_gb}, processes[{name, mb}], disks[{name, media, health, temperature, wear, power_on_hours, read_errors}], volumes[{letter, free_gb, total_gb, health}], gpu{name, driver, status}, stability{unexpected_shutdowns, whea, disk_errors, dumps, dumps_gb}, security{defender, signature_age_days, firewall_off, bitlocker}, reboot_pending, updates[]`.
- `measure_folders(categories: Dict[str, List[str]], limit: float) -> List[dict]` (puro su filesystem): `[{id, bytes, files}]`, cartelle inesistenti → 0.
- `collect_cleanup(ctx, system: dict) -> dict` — `categories: [{id, name, bytes, files}]` per `user_temp`, `windows_temp`, `update_cache`, `shader_cache` (D3D + NVIDIA), `crash_dumps` (utente), `system_dumps`, `recycle_bin` (PowerShell `Shell.Application` Namespace(10) somma `Size`); `volumes` da system; `recoverable_bytes`.
- `collect_integrity(system: dict, last_checks: Dict[str, dict]) -> dict` — `disks, volumes, stability, security, reboot_pending, bios_age_days, updates, checks` (ultimo run per `integrity.dism|sfc|disk_scan`).
- `collect_services(ctx) -> dict` — `totals{auto, manual, disabled, running, stopped}` (PowerShell `Get-CimInstance Win32_Service`), `managed[{name, group: "safe"|"manual"|"xbox"|"print", start, running}]`, `protected_present: int`, `backup_count: int`, `startup[names]`.

- [ ] **Step 1: Test**: `test_measure_folders_counts_only_old_files` (`os.utime` a 10 giorni fa per uno dei due file); `test_missing_folder_is_zero`; `test_empty_powershell_yields_errors` (`ctx.powershell_json` mock → `None`: `collect_services(ctx)["errors"]` non vuoto, nessuna eccezione); `test_translate_system_keys` (dati da `dati/report-*.json`-like sintetici: `["os"]["cpu"]`, `["stability"]["unexpected_shutdowns"]`).
- [ ] **Step 2:** → FAIL. **Step 3:** implementare (ogni PowerShell in `try` che accoda a `errors` su `TimeoutExpired`, `ValueError`, `OSError`). **Step 4:** → PASS.

### Task 4: Advisor — punteggi e raccomandazioni

**Files:** Create `wmm/agent/advisor.py` · Test `tests/test_advisor.py`

**Interfaces:**
- `Recommendation` dataclass: `id, area, title, reason, impact ("high"|"medium"|"low"), risk, action_id: Optional[str], priority: int` + `as_dict()`.
- `assess_cleanup(data) -> Tuple[int, List[Recommendation]]`, `assess_integrity(data)`, `assess_services(data)`; `ASSESSORS = {"cleanup": ..., "integrity": ..., "services": ...}`.
- `overall_score(scores: Dict[str, int]) -> int` — pesi cleanup 0.30, integrity 0.45, services 0.25, `round`.
- Regole (partenza 100, minimo 0, `reason` riporta il dato misurato):
  - Cleanup: −1 ogni 500 MB recuperabili (max −40); volume < `SOGLIA_SPAZIO_LIBERO` (15)% libero → −25 + racc. high; < 25% → −10. Racc. `cleanup.temp` se temp ≥ 200 MB; `cleanup.recycle_bin` ≥ 500 MB; `cleanup.dumps` ≥ 1 GB; `cleanup.components` se C: < 25% libero.
  - Integrity: disco non `Healthy` −40; wear ≥ 80 −25; read_errors > 0 −20; shutdown −3 cad. (max −15); WHEA −5 (max −20); disk_errors −3 (max −15); reboot_pending −5; BIOS > 730 gg −5 (consiglio, `action_id=None`); Defender off −20; firewall off −15; firme > 7 gg −5. Racc. `integrity.dism` e `integrity.sfc` se shutdown/WHEA/disk_errors > 0 o ultimo SFC non `ok` o più vecchio di 30 giorni / assente; `integrity.trim` se c'è un SSD.
  - Services: −3 per ogni servizio del gruppo `safe` non `disabled` (max −30); startup > 15 → −10, > 25 → −20, consiglio senza azione. Racc. `services.safe` se almeno uno non disabilitato.
  - Ordinamento: impact high→low, a parità `safe` prima.

- [ ] **Step 1: Test** con dati sintetici: `test_healthy_system_scores_100` (per ogni area); `test_volume_below_15_percent` (cleanup ≤ 75, prima racc. `impact == "high"`); `test_unhealthy_disk` (integrity ≤ 60); `test_old_bios_is_advice_only`; `test_score_never_negative`; `test_overall_score({"cleanup":100,"integrity":0,"services":100}) == 55`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementare. **Step 4:** → PASS.

### Task 5: Esecuzione azioni (jobs)

**Files:** Create `wmm/agent/jobs.py` · Test `tests/test_jobs.py`

**Interfaces:**
- `class RunInProgress(Exception)`, `class ConfirmationRequired(Exception)`.
- `JobManager(store: Store, machine_id: str, preview: bool = False)`:
  - `start(action_ids: List[str], origin: str, confirmed: bool) -> str` (uuid4 hex, thread daemon). Solleva `KeyError` per id sconosciuto, `ConfirmationRequired` se un'azione non è `safe` e `confirmed` è False, `RunInProgress` se un job è attivo (lock condiviso anche con `run_sync`).
  - `run_sync(action_ids, origin, confirmed) -> dict` (stesso flusso nel thread corrente; usato dalle pianificazioni).
  - `status(job_id) -> dict`: `{id, active, current, done, total, log: List[str], results: [{action_id, status, note, seconds, bytes_freed}]}`; `KeyError` se sconosciuto.
- Flusso: se c'è un'azione non `safe` → `punto_ripristino(ctx)` per primo; su `SequenzaFermata` tutti i risultati `skipped` con la nota e nessun `run` chiamato. Per ogni azione: `open_run` → `action.run(ctx)` (eccezione → `error`, `TimeoutExpired` → `error` "timed out") → `close_run` con `bytes_freed = max(0, free_after - free_before)` su C: e il log del passo. Log in memoria max 2000 righe.

- [ ] **Step 1: Test** (CATALOG patchato con azioni finte): `test_non_safe_without_confirmation_rejected`; `test_second_job_rejected_while_running` (azione finta in attesa su `threading.Event`); `test_failed_restore_point_skips_all`; `test_exception_becomes_error_and_is_stored`; `test_safe_actions_skip_restore_point`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementare. **Step 4:** → PASS.

### Task 6: Server HTTP e API

**Files:** Create `wmm/server/__init__.py`, `wmm/server/api.py`, `wmm.py`, `start_wmm.bat` · Test `tests/test_api.py`

**Interfaces:**
- `Agent(data_dir: Path, preview: bool, admin: bool)`: `store, jobs, machine_id, admin, preview, token (secrets.token_hex(16))`; `scan(area) -> dict` (collect → assess → `save_scan`; `collect_system` in cache 60 s; `integrity` riceve `store.last_runs_by_action`); `area_view(area) -> dict` (`{area, created, score, data, recommendations, actions (con last_run), trend, runs}`; se non c'è scan lo esegue); `dashboard() -> dict` (`{scores{cleanup, integrity, services, overall}, system, recommendations (top 6), runs (ultimi 10), trends{area: [...]}}`).
- `make_server(agent: Agent, port: int) -> ThreadingHTTPServer` su `127.0.0.1`. Dati in `dati/wmm.db` accanto al programma.
- Route (JSON, errori `{"error": "..."}`):
  - `GET /api/v1/agent/info` → `{name, version, machine_id, hostname, admin, preview}`
  - `GET /api/v1/dashboard`; `GET /api/v1/areas/{area}`; `POST /api/v1/areas/{area}/scan`
  - `GET /api/v1/actions`
  - `POST /api/v1/runs` `{actions, confirmed}` → 202 `{id}`; `POST /api/v1/runs/safe` `{area?}` → 202; `GET /api/v1/runs/{id}`
  - `GET /api/v1/history?area=&limit=` → `{runs, trends}`; `GET /api/v1/history/runs/{run_id}/log`
  - `GET /api/v1/export/{area|all}.{json|csv}` con `Content-Disposition: attachment`; CSV header `date,action,area,origin,status,note,bytes_freed`
  - Pianificazioni: Task 7.
  - Statici: `/` → `web/index.html` con `{{TOKEN}}` nel `<meta name="wmm-token">`; `/static/<path>` da `wmm/web/` (traversal bloccato: `resolve()` + controllo prefisso → 404).
- Sicurezza: `Host` non `127.0.0.1:<port>`/`localhost:<port>` → 403; non-GET senza `X-WMM-Token` corretto → 403; run/schedule senza admin (e non preview) → 409 `"Administrator rights are required"`; `RunInProgress` → 409; `ConfirmationRequired` → 400; area sconosciuta → 404.
- `wmm.py` (docstring d'uso in inglese): `--port 8765`, `--no-browser`, `--preview`, `--run-schedule ID`. Senza `--preview` e senza admin → rilancio elevato con `ShellExecuteW(..., "runas", ...)` come in `ottimizza_pc.riavvia_come_amministratore`. Apre `http://127.0.0.1:<port>/` con `webbrowser`. `start_wmm.bat`: `@echo off`, `cd /d "%~dp0"`, `python wmm.py`.

- [ ] **Step 1: Test** `tests/test_api.py` (server su porta 0 in thread, collector patchati con dati sintetici, store temporaneo, `admin=True`): `test_info`; `test_post_without_token_403`; `test_foreign_host_403`; `test_area_returns_score_and_recommendations`; `test_non_safe_run_without_confirmation_400`; `test_not_admin_409`; `test_export_csv_header`; `test_static_path_traversal_404` (`/static/../../ottimizza_pc.py`).
- [ ] **Step 2:** → FAIL. **Step 3:** implementare. **Step 4:** → PASS.

### Task 7: Pianificazioni (Utilità di pianificazione)

**Files:** Create `wmm/agent/scheduler.py`; Modify `wmm/server/api.py`, `wmm.py` · Test `tests/test_scheduler.py`

**Interfaces:**
- `task_name(schedule_id: int) -> str` → `"\\WindowsMaintenanceManager\\WMM-<id>"`.
- `task_xml(schedule: dict, python: str, script: str) -> str` (puro; schema `http://schemas.microsoft.com/windows/2004/02/mit/task`, indipendente dalla locale): `<StartBoundary>` = `at + ":00"`; `once` → `<TimeTrigger>`; `daily` → `<CalendarTrigger><ScheduleByDay><DaysInterval>1`; `weekly` → `<ScheduleByWeek><DaysOfWeek>` con `<Monday />` ecc. da `days` (`MON..SUN`); `<Principal>` `S-1-5-18` + `HighestAvailable`; `<Exec><Command>` python, `<Arguments>"<script>" --run-schedule <id></Arguments>`, `<WorkingDirectory>` cartella dello script; `StartWhenAvailable` true.
- `register(schedule, python, script) -> None` (XML in file temporaneo UTF-16, `schtasks /Create /F /TN <name> /XML <file>`, file eliminato; `RuntimeError` con l'output se codice ≠ 0); `unregister(id)`; `set_enabled(id, enabled)` (`/Change /ENABLE|/DISABLE`); `sync_state(store, script) -> Dict[int, str]` → `"ok"|"missing"|"path_changed"` (via `schtasks /Query /TN <name> /XML`).
- `run_schedule(schedule_id, store, jobs) -> int` (exit code): schedule assente → 2; disabilitato → 0; `jobs.run_sync([action_id], "schedule", confirmed=schedule["confirmed"])`; aggiorna `last_status`/`last_run`; `once` → `enabled=0`; ritorna 1 se c'è un `error`.
- API: `GET /api/v1/schedules` (con `sync`), `POST /api/v1/schedules` `{action_id, kind, at, days, confirmed}` (non `safe` senza `confirmed` → 400; salva → `register`; errore → riga eliminata e 500), `PATCH /api/v1/schedules/{id}` `{enabled}`, `DELETE /api/v1/schedules/{id}`, `POST /api/v1/schedules/{id}/resync` (re-register).
- `wmm.py --run-schedule ID` → `sys.exit(run_schedule(...))` senza server né browser.

- [ ] **Step 1: Test**: `test_xml_once_has_start_boundary` (`<StartBoundary>2026-11-05T03:00:00</StartBoundary>`, `<TimeTrigger>`); `test_xml_weekly_days` (`<Monday />`, `<Wednesday />` in `<DaysOfWeek>`); `test_xml_arguments_contain_id` (`--run-schedule 7`); `test_run_once_schedule_disables_itself` (jobs finto); `test_api_non_safe_schedule_without_confirmation_400`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementare. **Step 4:** → PASS.

### Task 8: Fondamenta GUI — shell, tema, client API, grafici

**Files:** Create `wmm/web/index.html`, `wmm/web/css/app.css`, `wmm/web/js/api.js`, `charts.js`, `ui.js`, `app.js`

**Interfaces:**
- `api.js`: `window.API = { get, post, patch, del }` → Promise JSON, header `X-WMM-Token` dal meta, errore → `Error(body.error)`.
- `charts.js`: `window.Charts` restituisce stringhe SVG (riusate dai report): `gauge(value, {label})`, `bars(series:[{label, value}], {format})`, `hbars(series, {format})`, `donut(series, {center})`, `line(series:[{name, points:[{x, y}]}], {min, max})`, `sparkline(values)`. Colori da variabili CSS con valori di fallback inline (così funzionano anche nei report), `<title>` accessibile.
- `ui.js`: `UI.esc`, `UI.kpi(title, value, sub, tone)`, `UI.card(title, bodyHtml, toolsHtml)`, `UI.table(columns, rows)`, `UI.riskBadge(risk)`, `UI.statusBadge(status)`, `UI.recommendations(list)`, `UI.toast(msg, tone)`, `UI.confirm(title, text) -> Promise<bool>`, `UI.scheduleDialog(action) -> Promise<{kind, at, days} | null>`, `UI.formatBytes(n)`, `UI.formatDate(iso)`.
- `app.js`: router hash `#/dashboard|cleanup|integrity|services|schedules|history|reports`; pagine `window.Pages[name] = { title, render(el) }`; top bar con hostname, machine_id, badge `Administrator`/`Read-only`, `Preview mode`; azioni condivise `App.runActions(ids, {confirmText})` e `App.schedule(action)`; drawer "Activity" con polling `/runs/{id}` ogni 1 s (barra di avanzamento + log).
- Stile (mia scelta): sidebar scura fissa con icone SVG inline e marchio "Windows Maintenance Manager", contenuto grigio chiaro, card bianche bordo sottile, font `Segoe UI Variable`/`Segoe UI`, accento `#0F6CBD`, stati verde/ambra/rosso, tema scuro con `prefers-color-scheme`, responsive fino a 1024 px, `@media print` senza sidebar e pulsanti.

- [ ] **Step 1:** Implementare.
- [ ] **Step 2:** `python wmm.py --preview --no-browser`, aprire `http://127.0.0.1:8765/`: shell visibile, navigazione senza errori in console.

### Task 9: Pagine Dashboard, Cleanup, Integrity, Services

**Files:** Create `wmm/web/js/pages/dashboard.js`, `cleanup.js`, `integrity.js`, `services.js`

Struttura comune pagina di area: header (titolo, ultima scansione, "Scan now", "Apply safe actions", "Export report") → KPI → grafici → "Recommended improvements" (con "Run"/"Schedule") → tabella azioni (title, risk, est. duration, last result, "Run", "Schedule") → trend punteggio + ultimi run dell'area.
- **Dashboard:** gauge overall + 3 gauge area, KPI (C: free, RAM free, uptime, open issues), donut occupazione C:, bars stabilità 30 gg, line trend per area, tabella system info, top recommendations, recent activity.
- **Cleanup:** KPI recoverable / C: free / freed last 30 days; hbars per categoria; donut volumi; bars spazio liberato per run.
- **Integrity:** KPI disk health / critical events 30d / reboot pending / BIOS age; tabella dischi; bars eventi stabilità; card Security (Defender, firewall, BitLocker, signatures); card Last checks (DISM/SFC/CHKDSK).
- **Services:** KPI total / running / disabled / in backup; donut per start type; tabella servizi gestiti (start, state, group); startup programs; "Restore from backup".
- "Run" su azione non `safe` → `UI.confirm` con `warning` → POST `confirmed:true`. "Schedule" → `UI.scheduleDialog` → POST schedules (con conferma per non `safe`).

- [ ] **Step 1:** Implementare.
- [ ] **Step 2:** Browser con `--preview`: ogni pagina mostra dati reali di questo PC, grafici leggibili in chiaro e scuro, nessun errore in console; run di `cleanup.temp` in preview visibile nel drawer.

### Task 10: Schedules, History, Reports ed export

**Files:** Create `wmm/web/js/report.js`, `wmm/web/js/pages/schedules.js`, `history.js`, `reports.js`

- `report.js`: `Report.build(scope: "dashboard"|"cleanup"|"integrity"|"services"|"full", {technician, notes}) -> Promise<string>` → HTML autonomo (CSS inline, SVG da `Charts`, header "Windows Maintenance Manager — <Scope> Report", hostname, machine_id, data, technician): executive summary con punteggi, grafici, dati descrittivi, recommendations, attività nel periodo, notes. `Report.download(scope, opts)` → `wmm-<scope>-<hostname>-<YYYYMMDD-HHMM>.html`; `Report.print(scope, opts)` → finestra + `print()` (PDF).
- **Schedules:** tabella (action, risk, type, next/last run, last result, sync, enabled) con toggle, delete, resync; "New schedule" (scelta azione + dialog).
- **History:** filtri area/periodo/stato; line trend; bars run per giorno per stato; tabella run con log espandibile; export CSV/JSON.
- **Reports:** scelta scope + "Technician" + "Notes for the customer"; anteprima in iframe; "Download HTML", "Print / Save as PDF", "Export CSV", "Export JSON". Il pulsante "Export report" delle pagine area usa `Report.download(area)`.

- [ ] **Step 1:** Implementare.
- [ ] **Step 2:** Verifica browser: creare schedule once di `cleanup.temp` → `schtasks /Query /TN "\WindowsMaintenanceManager\WMM-<id>"` lo trova; eliminarlo → sparisce. Report full scaricato e aperto offline: grafici visibili. Anteprima di stampa senza sidebar.

### Task 11: Verifica finale

- [ ] **Step 1:** `python -m unittest discover -v` dalla radice → tutti PASS, incluso `test_ottimizza_pc`.
- [ ] **Step 2:** Avvio reale con `start_wmm.bat` (UAC): giro di tutte le pagine, un'azione safe reale, una schedule lanciata con `schtasks /Run` e il suo esito visibile in History.
