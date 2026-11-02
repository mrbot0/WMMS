# Windows Maintenance Manager — Design

Data: 2026-11-02 · Base di partenza: `ottimizza_pc.py`

## Intento

Suite di manutenzione Windows per **tecnici IT**. Il tecnico la avvia sul PC del cliente,
la usa da una GUI web locale con aspetto enterprise, ottimizza le aree del sistema e
consegna un report con grafici di cosa ha trovato e cosa ha fatto.

## Obiettivi

- Pagine: **Dashboard, Pulizia, Integrità del sistema, Servizi, Pianificazioni, Storico, Report**.
- Ogni pagina di area (Pulizia, Integrità, Servizi) ha: grafici, dati descrittivi, un
  **punteggio 0–100** dell'area, i **miglioramenti proposti** e le azioni per ottimizzarla.
- La Dashboard riassume tutte le aree (punteggio globale, grafici, problemi principali,
  miglioramenti prioritari).
- **Storico** di analisi e interventi, con andamento nel tempo per ogni area.
- **Report esportabili** per ogni pagina e complessivo, con grafici: HTML autonomo,
  PDF (stampa del browser con foglio di stile dedicato), JSON e CSV.
- **Esecuzione delle azioni**:
  - **Ogni azione** (sicura o no) si può eseguire subito oppure **pianificare**:
    una tantum a data/ora, oppure ricorrente (giornaliera/settimanale).
  - Le azioni **sicure** possono partire da sole: pulsante "Applica tutte le sicure"
    e pianificazioni automatiche senza conferma.
  - Le azioni **meno sicure** partono solo su richiesta esplicita del tecnico
    (conferma con avvertenza al momento dell'esecuzione o della pianificazione).

## Non-obiettivi (per ora)

- Console centrale multi-PC: non si costruisce, ma l'architettura la prepara (vedi sotto).
- Autenticazione utenti, installer, servizio Windows permanente.

## Anti-obiettivi

- Toccare servizi protetti (Defender, Windows Update, firewall, rete, audio, GPU, ecc.):
  la lista `SERVIZI_PROTETTI` del programma esistente resta vincolante.
- Modifiche non sicure senza punto di ripristino o senza backup dello stato dei servizi.
- Dipendenze da internet: tutto deve funzionare offline.

## Vincoli

- **Offline**: nessuna CDN. Python **solo libreria standard** (http.server, sqlite3,
  json, threading). Grafici disegnati in **SVG da JavaScript vanilla**.
- Windows 10/11, Python 3.9+. Le azioni che modificano il sistema richiedono
  amministratore; senza, la suite funziona in sola lettura con avviso.
- Server in ascolto solo su `127.0.0.1`.

## Architettura

```
wmm/
  agent/          # "agente" locale: tutto ciò che una console centrale riuserà
    core.py       # Contesto, Esito, comandi, PowerShell (dal programma esistente)
    actions.py    # catalogo azioni: id, area, livello di rischio, funzione
    collectors.py # raccolta dati per area (pulizia, integrità, servizi, sistema)
    advisor.py    # punteggi e miglioramenti proposti (funzioni pure, testate)
    store.py      # SQLite: macchina, analisi, interventi, pianificazioni
    scheduler.py  # pianificazioni (thread interno)
    jobs.py       # esecuzione asincrona delle azioni con log in tempo reale
    report.py     # generazione report HTML/JSON/CSV
  server/
    api.py        # API REST JSON versionate /api/v1/...
  web/            # GUI statica (HTML/CSS/JS, SVG charts)
wmm.py            # avvio: server + apertura browser
```

- Ogni record nello storico porta un **machine_id** (hostname + GUID macchina), così
  i dati di più agenti si possono aggregare.
- La GUI parla **solo** con le API `/api/v1`. Una futura console centrale chiamerà le
  stesse API sugli agenti remoti (endpoint `GET /api/v1/agent/info` per identificarli).
- `ottimizza_pc.py` resta funzionante; la logica viene riusata nel pacchetto.

## Aree e contenuti

**Dashboard**: punteggio globale e per area (gauge), info sistema (OS, CPU, RAM,
uptime, BIOS), uso dischi, RAM, stabilità 30 giorni, sicurezza (Defender, firewall,
BitLocker), andamento punteggi nel tempo, top miglioramenti, ultimi interventi.

**Pulizia**: spazio recuperabile per categoria (temp utente, temp Windows, cache
Windows Update, cache shader, crash dump, cestino), grafico per categoria, spazio
liberato nel tempo, occupazione volumi.
Azioni: temporanei e cache (sicura), cestino (moderata), dump (moderata),
componenti DISM (moderata, lunga).

**Integrità**: salute dischi (SMART/usura/temperatura), eventi di stabilità
(spegnimenti, WHEA, errori disco), riavvio in sospeso, età BIOS, firme Defender,
esito ultime verifiche DISM/SFC/chkdsk.
Azioni: verifica disco senza riavvio e TRIM (sicure), DISM RestoreHealth, SFC
(moderate), riparazione disco al riavvio (alta).

**Servizi**: conteggi per tipo di avvio e stato, servizi gestiti con stato attuale,
servizi protetti, backup presente, programmi all'avvio.
Azioni: disattiva servizi sicuri (moderata), Xbox e stampa (alta), ripristino dal
backup (moderata).

**Pianificazioni**: elenco, creazione, sospensione, eliminazione; prossime esecuzioni
ed esito delle ultime.

## Rischio delle azioni

- `sicura`: nessuna perdita di dati né modifica di configurazione persistente.
  Può partire in automatico.
- `moderata` / `alta`: conferma esplicita con avvertenza (anche quando la si pianifica).
  Prima dell'esecuzione si crea/verifica il punto di ripristino; se fallisce,
  l'azione non parte.

## Miglioramenti proposti

L'advisor trasforma i dati raccolti in raccomandazioni con: titolo, motivo (dato
misurato), impatto, rischio, azione collegata (se esiste), ordinate per priorità.
Alcune sono solo consigli (es. aggiornare il BIOS, ridurre i programmi all'avvio).

## Pianificazione

Le pianificazioni devono funzionare **anche a programma chiuso** (decisione dell'utente).

- Ogni pianificazione è salvata in SQLite e registrata nell'**Utilità di pianificazione
  di Windows** (`schtasks`, cartella `\WindowsMaintenanceManager\`, esecuzione con
  privilegi elevati come SYSTEM o utente amministratore).
- Il task lancia l'agente in modalità senza interfaccia:
  `python wmm.py --esegui-pianificazione <id>`, che esegue l'azione, applica le stesse
  regole di sicurezza (punto di ripristino per le azioni non sicure) e salva l'esito
  nello storico.
- La GUI crea, modifica, sospende ed elimina le pianificazioni mantenendo allineati
  SQLite e Utilità di pianificazione; all'avvio segnala le differenze (task rimossi a mano).
- Gli esiti delle esecuzioni compaiono nello storico e nella pagina Pianificazioni.

## Decisioni prese da me (verificabili)

- Python standard library + JS vanilla + SVG (offline, nessuna installazione).
- SQLite per lo storico, cartella `dati/` accanto al programma (portabile).
- PDF via stampa del browser, non generato lato server.
- Porta predefinita 8765, solo localhost.
- I task pianificati usano il percorso assoluto di Python e del programma: se la
  cartella viene spostata, la GUI propone di riallinearli.
- Interfaccia, report ed export **in inglese** (decisione dell'utente); anche nuovo codice,
  API e chiavi JSON in inglese (mia scelta). Pagine: Dashboard, Cleanup, System Integrity,
  Services, Schedules, History, Reports.
