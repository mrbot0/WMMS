/* Italian interface. The console is written in English; this layer translates what is on screen (text, title,
   placeholder, aria-label) from a dictionary of exact phrases plus a few rules for dynamic text ("5 days ago",
   "Programs (90)"). Data never changes: paths, commands, logs, program names and anything in .cell-mono stay as they are.
   Settings › Appearance › Language: automatic (the browser language), English or Italiano. */
(function () {
  "use strict";
  var pref = null;
  try { pref = JSON.parse(localStorage.getItem("wmm.lang") || "null"); } catch (e) { pref = null; }
  var lang = pref === "en" || pref === "it" ? pref : /^it\b/i.test(navigator.language || "") ? "it" : "en";

  var IT = {
    // ---------- menu, categories, pages ----------
    "Overview": "Panoramica", "Optimize": "Ottimizza", "Health": "Salute", "System": "Sistema", "Operations": "Operazioni",
    "Help & settings": "Aiuto e impostazioni", "Dashboard": "Dashboard", "Recommendations": "Consigli", "Performance": "Prestazioni",
    "Cleanup": "Pulizia", "Storage": "Archiviazione", "Startup & Apps": "Avvio e app", "Applications": "Applicazioni", "Services": "Servizi",
    "System Integrity": "Integrità del sistema", "Security": "Sicurezza", "Updates & Drivers": "Aggiornamenti e driver", "Network": "Rete",
    "Hardware": "Hardware", "Event Viewer": "Visualizzatore eventi", "Task Manager": "Gestione attività", "Registry": "Registro",
    "Toolbox": "Strumenti", "Activity": "Attività", "Playbooks": "Sequenze", "Schedules": "Pianificazioni", "Scripts": "Script",
    "History": "Cronologia", "Reports": "Report", "Support": "Supporto", "Settings": "Impostazioni",
    "The state of this PC at a glance and the improvements worth doing first.": "Lo stato di questo PC a colpo d'occhio e i miglioramenti da fare per primi.",
    "Make the PC faster and free space: performance, cleanup, disks, startup and services.": "Rendi il PC più veloce e libera spazio: prestazioni, pulizia, dischi, avvio e servizi.",
    "Keep Windows sound and safe: system files, security, updates, drivers and network.": "Mantieni Windows integro e sicuro: file di sistema, sicurezza, aggiornamenti, driver e rete.",
    "Look inside the PC: hardware and temperatures, event logs, running processes and services, and the registry.": "Guarda dentro il PC: hardware e temperature, registri eventi, processi e servizi in esecuzione, registro.",
    "Run, combine, schedule and document the maintenance work.": "Esegui, combina, pianifica e documenta la manutenzione.",
    "User guide, troubleshooting, appearance, installation and start-up options.": "Guida, risoluzione dei problemi, aspetto, installazione e opzioni di avvio.",
    "Overall health, live system, key figures and this visit.": "Salute generale, sistema in tempo reale, numeri chiave e questa visita.",
    "Every improvement found by the scans, sorted by impact, with one-click fixes.": "Ogni miglioramento trovato dalle scansioni, ordinato per impatto, con correzioni in un clic.",
    "Memory, CPU, power plans, visual effects and 80+ speed tools.": "Memoria, CPU, piani di risparmio energia, effetti visivi e oltre 80 strumenti di velocità.",
    "Temporary files, caches, crash dumps and obsolete Windows components.": "File temporanei, cache, dump degli arresti e componenti di Windows obsoleti.",
    "Where the space goes, disk health, SMART and 30+ disk tools.": "Dove va lo spazio, salute dei dischi, SMART e oltre 30 strumenti per i dischi.",
    "Programs that start with Windows and the installed applications.": "Programmi che partono con Windows e applicazioni installate.",
    "Unsafe and unused programs, uninstall, Store apps, app updates and browser caches.": "Programmi insicuri e inutilizzati, disinstallazione, app dello Store, aggiornamenti e cache dei browser.",
    "Unnecessary services, with a backup of every change.": "Servizi non necessari, con un backup di ogni modifica.",
    "DISM, SFC, disk checks, crashes, reliability and the event log.": "DISM, SFC, controllo dei dischi, arresti anomali, affidabilità e registro eventi.",
    "Defender, firewall, BitLocker, TPM, Secure Boot and hardening.": "Defender, firewall, BitLocker, TPM, Secure Boot e protezione avanzata.",
    "Pending updates, drivers, devices with problems and app updates.": "Aggiornamenti in sospeso, driver, dispositivi con problemi e aggiornamenti delle app.",
    "Adapters, latency, DNS, Wi-Fi and network repairs.": "Schede di rete, latenza, DNS, Wi-Fi e riparazioni di rete.",
    "Every component with its hardware IDs, driver search, live temperatures and fans.": "Ogni componente con i suoi ID hardware, ricerca driver, temperature e ventole in tempo reale.",
    "Critical, hardware, application and service events, filterable and live.": "Eventi critici, hardware, delle applicazioni e dei servizi, filtrabili e in tempo reale.",
    "Every process and service with live usage; end, prioritize or start them.": "Ogni processo e servizio con l'uso in tempo reale: terminali, cambia priorità o avviali.",
    "Browse, search and edit the registry, with a backup before every change.": "Sfoglia, cerca e modifica il registro, con un backup prima di ogni modifica.",
    "Every tool by area: fixes and read-only reports.": "Ogni strumento per area: correzioni e report di sola lettura.",
    "Runs and scans in progress, with their live log.": "Esecuzioni e scansioni in corso, con il loro registro in tempo reale.",
    "Ready-made sequences: quick tune-up, full maintenance, repair, hardening.": "Sequenze pronte: messa a punto rapida, manutenzione completa, riparazione, protezione.",
    "Maintenance that runs on its own through Windows Task Scheduler.": "Manutenzione che parte da sola tramite l'Utilità di pianificazione di Windows.",
    "Your .bat scripts run now or at a set time, ready-made scripts and the shutdown timer.": "I tuoi script .bat, subito o a un'ora stabilita, script pronti e timer di spegnimento.",
    "Every run with its result, freed space and log.": "Ogni esecuzione con risultato, spazio liberato e registro.",
    "Branded reports for the customer, as PDF, HTML, CSV or JSON.": "Report personalizzati per il cliente, in PDF, HTML, CSV o JSON.",
    "User guide, FAQ, troubleshooting and diagnostics for support.": "Guida, domande frequenti, risoluzione dei problemi e diagnostica per l'assistenza.",
    "Report branding, appearance, guides, start-up and installation.": "Intestazione dei report, aspetto, guide, avvio e installazione.",

    // ---------- top bar, status bar, common buttons ----------
    "Scan all": "Scansiona tutto", "Scan all areas": "Scansiona tutte le aree", "Search or run a command": "Cerca o esegui un comando",
    "Agent connected": "Agente connesso", "Agent not reachable": "Agente non raggiungibile", "Preview mode": "Modalità anteprima", "Administrator": "Amministratore",
    "Read-only": "Sola lettura", "Auto-refresh": "Aggiornamento automatico", "commands": "comandi", "shortcuts": "scorciatoie",
    "Cancel": "Annulla", "Close": "Chiudi", "Save": "Salva", "Copy": "Copia", "Edit": "Modifica", "Delete": "Elimina", "Rename": "Rinomina", "Create": "Crea",
    "Run": "Esegui", "Run now": "Esegui ora", "Run selected": "Esegui selezionati", "Apply selected": "Applica selezionati", "Refresh": "Aggiorna", "Back": "Indietro",
    "Next": "Avanti", "Previous": "Precedente", "Show": "Mostra", "Hide": "Nascondi", "Search": "Cerca", "Search…": "Cerca…", "Reset": "Ripristina", "Clear": "Svuota",
    "Export": "Esporta", "Import": "Importa", "Restore": "Ripristina", "Restart": "Riavvia", "Shut down": "Spegni", "Start": "Avvia", "Stop": "Ferma", "Check": "Controlla",
    "Measure": "Misura", "Confirm": "Conferma", "Got it": "Ho capito", "Not now": "Non ora", "Full guide": "Guida completa", "Read again": "Rileggi", "Test": "Prova",
    "Schedule": "Pianifica", "Update": "Aggiorna", "Uninstall": "Disinstalla", "Uninstall…": "Disinstalla…", "Remove": "Rimuovi", "Remove entry": "Rimuovi voce",
    "Remove selected": "Rimuovi selezionati", "Keep everything": "Tieni tutto", "Open location": "Apri percorso", "Copy path": "Copia percorso",
    "Request access": "Richiedi accesso", "Restart as administrator": "Riavvia come amministratore", "Retry": "Riprova", "Updating…": "Aggiornamento…",
    "Updated": "Aggiornato", "Simulated": "Simulato", "Scan again": "Scansiona di nuovo", "Update preview": "Aggiorna anteprima",
    "Download HTML": "Scarica HTML", "Print / Save as PDF": "Stampa / Salva come PDF", "Copy as text": "Copia come testo", "Email draft": "Bozza email",
    "Copy summary": "Copia riepilogo", "Copy for support": "Copia per l'assistenza", "Copy checklist": "Copia elenco", "Again": "Di nuovo", "Undo…": "Annulla…",
    "View": "Mostra", "Copy log": "Copia registro", "Loading…": "Caricamento…", "Previous / next tab of the page": "Scheda precedente / successiva della pagina",
    "Rows": "Righe", "Nothing to show.": "Niente da mostrare.", "No match.": "Nessun risultato.", "Select visible": "Seleziona visibili",
    "Save as playbook": "Salva come sequenza", "Reset filters": "Azzera filtri", "Safest first": "Più sicuri prima", "Favorites": "Preferiti",

    // ---------- statuses, risk, levels ----------
    "Success": "Riuscito", "Warning": "Avviso", "Warnings": "Avvisi", "Error": "Errore", "Errors": "Errori", "Skipped": "Saltato", "Preview": "Anteprima",
    "Running": "In esecuzione", "Stopped": "Fermo", "Paused": "In pausa", "Ready": "Pronto", "Disabled": "Disattivato", "Enabled": "Attivo", "On": "Attivo", "Off": "Spento",
    "Safe": "Sicuro", "Moderate": "Moderato", "High risk": "Rischio alto", "High": "Alto", "Medium": "Medio", "Low": "Basso", "High impact": "Impatto alto",
    "Medium impact": "Impatto medio", "Low impact": "Impatto basso", "Critical": "Critico", "Information": "Informazione", "Verbose": "Dettaglio", "Healthy": "Integro",
    "Needs attention": "Da controllare", "Needs maintenance": "Richiede manutenzione", "Unknown": "Sconosciuto", "None": "Nessuno", "Never": "Mai", "never": "mai",
    "Manual": "Manuale", "Automatic": "Automatico", "Scheduled": "Pianificato", "Passed": "Superato", "In progress": "In corso", "Completed today": "Completate oggi",
    "Failed today": "Non riuscite oggi", "Unsafe": "Insicuro", "Review": "Da rivedere", "To review": "Da rivedere", "In use": "In uso", "Not used": "Non usato",
    "Today": "Oggi", "Yesterday": "Ieri", "just now": "adesso", "Protected": "Protetto", "Not protected": "Non protetto", "Encrypted": "Cifrato",

    // ---------- table headers and filters ----------
    "Date": "Data", "Action": "Azione", "Origin": "Origine", "Result": "Risultato", "Note": "Nota", "Freed": "Liberato", "Log": "Registro",
    "Name": "Nome", "Program": "Programma", "Publisher": "Editore", "Version": "Versione", "Installed": "Installato", "Size": "Dimensione", "Last used": "Ultimo uso",
    "Location": "Posizione", "Command": "Comando", "State": "Stato", "Status": "Stato", "Author": "Autore", "Folder": "Cartella", "Task": "Attività", "Type": "Tipo",
    "Service": "Servizio", "Start type": "Tipo di avvio", "Description": "Descrizione", "Source": "Origine", "Level": "Livello", "Message": "Messaggio", "Time": "Ora",
    "When": "Quando", "Why": "Perché", "Risk": "Rischio", "Impact": "Impatto", "Reason": "Motivo", "Improvement": "Miglioramento", "Score": "Punteggio",
    "Before": "Prima", "After": "Dopo", "Change": "Variazione", "Average": "Media", "Value": "Valore", "Data": "Dati", "Key": "Chiave",
    "Downloaded": "Scaricato", "Available": "Disponibile", "Device": "Dispositivo", "Maker": "Produttore", "Manufacturer": "Produttore",
    "Process": "Processo", "Memory": "Memoria", "Processor": "Processore", "Disk": "Disco", "Disks": "Dischi", "Volume": "Volume", "Volumes": "Volumi", "Free": "Libero",
    "Used": "Usato", "Temperature": "Temperatura", "Uptime": "Tempo di attività", "Kind": "Tipo", "For": "Per", "Website": "Sito web", "Safety": "Sicurezza",
    "Next run": "Prossima esecuzione", "Last run": "Ultima esecuzione", "Created": "Creato", "Restore point": "Punto di ripristino",
    "Restore points": "Punti di ripristino", "All results": "Tutti i risultati", "All origins": "Tutte le origini", "All states": "Tutti gli stati",
    "All kinds": "Tutti i tipi", "Any use": "Qualsiasi uso", "All Store apps": "Tutte le app dello Store", "Preinstalled extras": "Extra preinstallati",
    "Others": "Altri", "All": "Tutti", "All types": "Tutti i tipi", "All levels": "Tutti i livelli", "All logs": "Tutti i registri", "All sources": "Tutte le origini",
    "All start types": "Tutti i tipi di avvio", "Any status": "Qualsiasi stato", "Any state": "Qualsiasi stato", "Any": "Qualsiasi",

    // ---------- KPIs and cards that appear on many pages ----------
    "Overall health": "Salute generale", "Recommended improvements": "Miglioramenti consigliati", "Optimization actions": "Azioni di ottimizzazione",
    "Score trend": "Andamento del punteggio", "Recent activity": "Attività recente", "Improvements": "Miglioramenti", "Tools": "Strumenti",
    "Last scan": "Ultima scansione", "Key figures": "Numeri chiave", "Live system": "Sistema in tempo reale", "This visit": "Questa visita",
    "Today on this PC": "Oggi su questo PC", "Visit checklist": "Elenco della visita", "Health by area": "Salute per area", "Scores by area": "Punteggi per area",
    "Areas at a glance": "Le aree a colpo d'occhio", "Top recommended improvements": "Principali miglioramenti consigliati", "Security posture": "Stato della sicurezza",
    "Stability · 30 days": "Stabilità · 30 giorni", "Unexpected shutdowns": "Arresti imprevisti", "Pending updates": "Aggiornamenti in sospeso",
    "Free on C:": "Libero su C:", "CPU in use": "CPU in uso", "Free memory": "Memoria libera", "Space freed": "Spazio liberato", "Freed in 30 days": "Liberato in 30 giorni",
    "Recoverable": "Recuperabile", "Recoverable space by category": "Spazio recuperabile per categoria", "Startup programs": "Programmi all'avvio",
    "Installed applications": "Applicazioni installate", "Third-party scheduled tasks": "Attività pianificate di terze parti", "Third-party tasks": "Attività di terze parti",
    "Publishers": "Editori", "Installs per year": "Installazioni per anno", "Largest applications": "Applicazioni più grandi", "Physical disks": "Dischi fisici",
    "Network adapters": "Schede di rete", "Network latency": "Latenza di rete", "Internet latency": "Latenza Internet", "Packet loss": "Pacchetti persi",
    "Devices with problems": "Dispositivi con problemi", "Third-party drivers": "Driver di terze parti", "Memory modules": "Moduli di memoria",
    "Temperatures and fans": "Temperature e ventole", "Hardware sensors": "Sensori hardware", "Running services": "Servizi in esecuzione",
    "Report options": "Opzioni del report", "Data export": "Esportazione dati", "Technician notes": "Note del tecnico", "Scheduled runs": "Esecuzioni pianificate",
    "New schedule": "Nuova pianificazione", "My scripts": "I miei script", "Ready-made scripts": "Script pronti", "New script": "Nuovo script",
    "Activity calendar": "Calendario attività", "Before / after": "Prima / dopo", "Most run actions": "Azioni più eseguite", "Success rate": "Percentuale di successo",
    "Runs per day": "Esecuzioni al giorno",

    // ---------- Applications page ----------
    "What is installed, what is unsafe and what you no longer use": "Cosa è installato, cosa è insicuro e cosa non usi più",
    "Check app updates": "Controlla aggiornamenti app", "Not used for months": "Non usati da mesi", "Browser caches": "Cache dei browser",
    "Programs": "Programmi", "Updates": "Aggiornamenti", "Store apps": "App dello Store", "Browsers & leftovers": "Browser e residui", "Suggestions": "Suggerimenti",
    "Kinds of program": "Tipi di programma", "Use": "Uso", "Largest programs": "Programmi più grandi", "Installed in the last 30 days": "Installati negli ultimi 30 giorni",
    "Installed programs": "Programmi installati", "New (30 days)": "Nuovi (30 giorni)", "Over 1 GB": "Oltre 1 GB", "Start with Windows": "Avvio con Windows",
    "Leftovers": "Residui", "End of support": "Fine supporto", "Versions with known holes": "Versioni con falle note",
    "Adware and unwanted programs": "Adware e programmi indesiderati", "Remote access": "Accesso remoto",
    "Optimizers and driver updaters": "Ottimizzatori e aggiornatori di driver", "Unknown publisher": "Editore sconosciuto",
    "Support ending soon": "Supporto in scadenza", "How the verdict works": "Come funziona il giudizio", "App updates (winget)": "Aggiornamenti app (winget)",
    "Update all": "Aggiorna tutto", "Microsoft Store apps": "App del Microsoft Store", "Clear cache": "Svuota cache", "Clear all caches": "Svuota tutte le cache",
    "Setup files left in Downloads": "File di installazione rimasti in Download", "Update the rules": "Aggiorna le regole", "Preinstalled extra": "Extra preinstallato",
    "Application": "Applicazione", "Driver / system": "Driver / sistema", "Optimizer": "Ottimizzatore", "Unwanted": "Indesiderato",
    "No use recorded": "Nessun uso registrato", "Startup": "Avvio", "Open": "Aperto", "Registry key": "Chiave di registro", "This account only": "Solo questo account",
    "Every account": "Tutti gli account", "Open System Restore": "Apri Ripristino configurazione di sistema", "Go on without it": "Continua senza",
    "No restore point": "Nessun punto di ripristino", "Command (read from Windows):": "Comando (letto da Windows):",
    "Creating a restore point first: it can take a minute.": "Prima creo un punto di ripristino: può volerci un minuto.",
    "Page refreshed.": "Pagina aggiornata.", "Scan completed.": "Scansione completata.", "Nothing was changed.": "Non è stato modificato nulla.",
    "Folder opened in File Explorer.": "Cartella aperta in Esplora file.", "Page refreshed: you were away for a while.": "Pagina aggiornata: eri via da un po'.",

    // ---------- reports ----------
    "Technician": "Tecnico", "Notes for the customer": "Note per il cliente", "Changes since": "Modifiche dal", "Before / After": "Prima / Dopo",
    "Full Maintenance": "Manutenzione completa", "Executive Summary": "Riepilogo", "Result of the maintenance": "Risultato della manutenzione",
    "Health before": "Salute prima", "Health after": "Salute dopo", "Operations done": "Operazioni eseguite", "What was done": "Cosa è stato fatto",
    "Operations with errors": "Operazioni con errori", "Still recommended": "Ancora consigliato", "Executive summary": "Riepilogo", "Generated": "Generato",
    "Machine ID": "ID macchina", "80 or more is healthy.": "80 o più è un buon punteggio.", "No improvements needed.": "Nessun miglioramento necessario.",
    "No actions were run in this period.": "Nessuna azione eseguita in questo periodo.", "No change was made in this period.": "Nessuna modifica in questo periodo.",
    "Operating system": "Sistema operativo", "Motherboard / firmware": "Scheda madre / firmware", "Graphics": "Grafica",

    // ---------- settings and preferences ----------
    "Appearance": "Aspetto", "Behaviour": "Comportamento", "Notifications": "Notifiche", "Start-up": "Avvio", "Dashboard sections": "Sezioni della dashboard",
    "Report branding": "Intestazione dei report", "Language": "Lingua", "Light": "Chiaro", "Dark": "Scuro", "Like Windows": "Come Windows", "Compact": "Compatta",
    "Comfortable": "Comoda", "Quiet hours": "Ore di silenzio", "Maintenance": "Manutenzione", "Diagnostics": "Diagnostica",
    "Keyboard shortcuts": "Scorciatoie da tastiera", "Command palette": "Tavolozza comandi", "This help": "Questo aiuto", "Close dialogs": "Chiudi le finestre",

    // ---------- console functions ----------
    "Notes for this PC": "Note per questo PC", "On this page": "In questa pagina", "On this page: jump to a card": "In questa pagina: vai a una sezione",
    "Search the table of this page": "Cerca nella tabella della pagina", "Show page errors": "Mostra errori della pagina", "Page errors": "Errori della pagina",
    "Copy a link to this tab": "Copia un link a questa scheda", "Open the Toolbox": "Apri gli strumenti", "Open the user guide": "Apri la guida",
    "Show activity": "Mostra attività", "Export full report": "Esporta report completo", "Apply all safe actions": "Applica tutte le azioni sicure",
    "Run every diagnostic report": "Esegui tutti i report diagnostici", "What's new in this version": "Novità di questa versione",
    "Toggle light / dark theme": "Tema chiaro / scuro", "Collapse or expand all cards": "Comprimi o espandi tutte le sezioni", "Copy the machine ID": "Copia l'ID macchina",
    "Copy a link to this page": "Copia un link a questa pagina", "Copy this page as text": "Copia questa pagina come testo",
    "Focus mode (hide the menu)": "Modalità concentrazione (nascondi il menu)", "Stop Windows Maintenance Manager": "Arresta Windows Maintenance Manager",
    "Compact density": "Densità compatta", "Dashboard auto-refresh": "Aggiornamento automatico della dashboard", "Recent pages": "Pagine recenti",
    "Recent commands": "Comandi recenti", "Categories": "Categorie", "Pages": "Pagine", "Commands": "Comandi", "Preferences": "Preferenze",
    "Favorite actions": "Azioni preferite", "Windows settings": "Impostazioni di Windows", "Welcome": "Benvenuto", "Take the tour": "Fai il giro guidato",
    "Start the tour": "Inizia il giro", "Skip tour": "Salta il giro", "How this page works": "Come funziona questa pagina", "Guide for this page": "Guida di questa pagina",
    "Back to top": "Torna su", "Search pages, actions and commands…": "Cerca pagine, azioni e comandi…", "navigate": "sposta", "open": "apri", "close": "chiudi",
    "Search programs, publishers, versions…": "Cerca programmi, editori, versioni…", "Search Store apps…": "Cerca app dello Store…", "Search updates…": "Cerca aggiornamenti…",
    "Search startup programs…": "Cerca programmi all'avvio…", "Search applications or publishers…": "Cerca applicazioni o editori…", "Search tasks…": "Cerca attività…"
  };

  // Dynamic text: [pattern, replacement or function]. Applied when the exact phrase is not in the dictionary.
  var MONTHS = { Jan: "gen", Feb: "feb", Mar: "mar", Apr: "apr", May: "mag", Jun: "giu", Jul: "lug", Aug: "ago", Sep: "set", Oct: "ott", Nov: "nov", Dec: "dic" };
  var RULES = [
    [/^(\d+) days ago$/, "$1 giorni fa"], [/^(\d+) months ago$/, "$1 mesi fa"], [/^(\d+) min ago$/, "$1 min fa"], [/^(\d+) h ago$/, "$1 h fa"],
    [/^(\d+) programs and (\d+) Store apps · scanned (.+)$/, "$1 programmi e $2 app dello Store · scansione $3"],
    [/^(\d+) Store apps · (.+) reported$/, "$1 app dello Store · $2 dichiarati"], [/^(\d+) browsers$/, "$1 browser"],
    [/^(\d+) unsafe programs?$/, "$1 programmi insicuri"], [/^(\d+) programs? not used for months$/, "$1 programmi non usati da mesi"],
    [/^(\d+) preinstalled Store apps?$/, "$1 app dello Store preinstallate"], [/^(\d+) leftover entr(?:y|ies)$/, "$1 voci rimaste"],
    [/^Oldest area scan: (.+)$/, function (m, when) { return "Scansione più vecchia: " + (translate(when) || when); }],
    [/^v([\d.]+) · (\d+) tools$/, "v$1 · $2 strumenti"],
    [/^Preview mode: the (uninstall|removal|cleanup|update) was simulated, nothing changed\.$/, function (m, what) {
      return "Modalità anteprima: " + { uninstall: "la disinstallazione", removal: "la rimozione", cleanup: "la pulizia", update: "l'aggiornamento" }[what] +
        " è stata simulata, nulla è cambiato.";
    }],
    [/^(Uninstall|Remove|Undo|Leftovers of) (.+)$/, function (m, verb, what) {
      return { Uninstall: "Disinstalla ", Remove: "Rimuovi ", Undo: "Annulla ", "Leftovers of": "Residui di " }[verb] + what;
    }],
    [/^Protected by restore point #(\d+): History › Undo brings the PC back to it\.$/, "Protetto dal punto di ripristino n. $1: Cronologia › Annulla riporta il PC a quel momento."], [/^Health: (\d+) warnings$/, "Salute: $1 avvisi"], [/^Health: (\d+) failed$/, "Salute: $1 non superati"],
    [/^Health: all checks passed$/, "Salute: tutti i controlli superati"],
    [/^Last scan (.+)$/, function (m, when) { return "Ultima scansione " + (translate(when) || when); }], [/^(\d+) improvement\(s\)$/, "$1 miglioramenti"],
    [/^(\d+)–(\d+) of (\d+)(.*)$/, function (m, a, b, c, rest) { return a + "–" + b + " di " + c + rest.replace("filtered from", "filtrati da"); }],
    // "Programs (90)", "Security (9)": translate the label, keep the count.
    [/^(.+?) \(([\d.,]+(?: [KMGT]?B)?)\)$/, function (m, label, n) { return IT[label] ? IT[label] + " (" + n + ")" : m; }],
    // "Label:" and "Label…": the same phrase with punctuation.
    [/^(.+?)([:…])$/, function (m, label, p) { return IT[label] ? IT[label] + p : m; }],
    // Dates written by UI.formatDate ("Nov 03, 2026, 19:24").
    [/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}), (\d{4})(.*)$/, function (m, mon, d, y, rest) { return d + " " + MONTHS[mon] + " " + y + rest; }]
  ];

  var SKIP = "pre, code, textarea, script, style, .cell-mono, .log, .notes-area, [data-no-i18n], .kbd";
  var ATTRS = ["title", "placeholder", "aria-label", "data-tip"];

  function translate(text) {
    var core = text.trim();
    if (!core || core.length > 400 || !/[A-Za-z]/.test(core)) return null;
    var out = Object.prototype.hasOwnProperty.call(IT, core) ? IT[core] : null;
    for (var i = 0; out == null && i < RULES.length; i++) {
      if (!RULES[i][0].test(core)) continue;
      var t = core.replace(RULES[i][0], RULES[i][1]);
      if (t !== core) out = t;
    }
    return out == null ? null : text.replace(core, out);
  }
  function skipped(el) { return !!(el && el.closest && el.closest(SKIP)); }
  function attrs(el) {
    ATTRS.forEach(function (a) {
      var v = el.getAttribute(a);
      if (v) { var t = translate(v); if (t != null && t !== v) el.setAttribute(a, t); }
    });
  }
  function text(node) {
    var t = translate(node.nodeValue);
    if (t != null && t !== node.nodeValue) node.nodeValue = t;
  }
  function translateNode(node) {
    if (node.nodeType === 3) { if (!skipped(node.parentNode)) text(node); return; }
    if (node.nodeType !== 1 || skipped(node)) return;
    attrs(node);
    var walker = document.createTreeWalker(node, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null), n;
    while ((n = walker.nextNode())) {
      if (n.nodeType === 1) { if (!skipped(n)) attrs(n); } else if (!skipped(n.parentNode)) text(n);
    }
  }

  /* A whole HTML document (the customer report): same dictionary, same rules. */
  function translateHtml(html) {
    if (lang !== "it" || !window.DOMParser) return html;
    var doc = new DOMParser().parseFromString(html, "text/html");
    translateNode(doc.body);
    var title = translate(doc.title || "");
    if (title) doc.title = title;
    doc.documentElement.setAttribute("lang", "it");
    return "<!doctype html>" + doc.documentElement.outerHTML;
  }

  function start() {
    document.documentElement.setAttribute("lang", lang);
    if (lang !== "it") return;
    translateNode(document.body);
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        if (m.type === "childList") m.addedNodes.forEach(translateNode); else translateNode(m.target);
      });
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  window.I18N = {
    lang: function () { return lang; },
    choice: function () { return pref || "auto"; },
    set: function (value) {
      try { localStorage.setItem("wmm.lang", JSON.stringify(value === "auto" ? null : value)); } catch (e) { /* storage unavailable */ }
      location.reload();
    },
    t: function (s) { return lang === "it" ? (translate(s) || s) : s; },
    translateHtml: translateHtml,
    size: function () { return Object.keys(IT).length; }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
