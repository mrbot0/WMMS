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
    "Search startup programs…": "Cerca programmi all'avvio…",
    // ---------- network scanner ----------
    "Network scanner": "Scanner di rete", "Scan the network": "Scansiona la rete", "Devices": "Dispositivi", "New devices": "Nuovi dispositivi",
    "Devices on the network": "Dispositivi in rete", "Open web page": "Apri pagina web", "Not seen in the last scan": "Non visti nell'ultima scansione",
    "Router / gateway": "Router / gateway", "This PC": "Questo PC", "Printer": "Stampante", "Camera": "Telecamera", "TV / media": "TV / multimedia",
    "Smart home device": "Dispositivo domotico", "Windows PC": "PC Windows", "Phone or tablet": "Telefono o tablet", "Device with a web page": "Dispositivo con pagina web",
    "Every device on your network: name, maker, open ports, web page and new arrivals.": "Ogni dispositivo della tua rete: nome, produttore, porte aperte, pagina web e nuovi arrivi.",
    "New": "Nuovo", "Open ports": "Porte aperte", "First seen": "Visto la prima volta", "Response": "Risposta",
    "With a web page": "Con pagina web", "Services to check": "Servizi da controllare", "none": "nessuna", "IP address": "Indirizzo IP",
    "TV, phone or appliance": "TV, telefono o elettrodomestico", "Amazon device (Echo, Fire TV, Kindle)": "Dispositivo Amazon (Echo, Fire TV, Kindle)",
    "Mac / Apple device": "Mac / dispositivo Apple", "since the previous scan": "dalla scansione precedente",
    "router, printer, NAS settings": "impostazioni di router, stampanti, NAS", "Telnet, FTP, VNC, Remote Desktop": "Telnet, FTP, VNC, Desktop remoto",
    "Search IP, name, maker, type…": "Cerca IP, nome, produttore, tipo…", "New since the previous scan": "Nuovo dalla scansione precedente",
    "Switched off, out of range or gone": "Spenti, fuori portata o rimossi",
    // ---------- Wi-Fi and Bluetooth scanners ----------
    "Network devices": "Dispositivi in rete", "Wi-Fi": "Wi-Fi", "Bluetooth": "Bluetooth", "Scan Wi-Fi": "Scansiona Wi-Fi", "Scan Bluetooth": "Scansiona Bluetooth",
    "Wi-Fi networks nearby": "Reti Wi-Fi nei dintorni", "Networks": "Reti", "Your network": "La tua rete", "Open or weak": "Aperte o deboli",
    "Best channel": "Canale migliore", "Channels in use": "Canali in uso", "Signal": "Segnale", "Band": "Banda", "Channel": "Canale",
    "Stations": "Dispositivi connessi", "Connected": "Connesso", "Hidden network": "Rete nascosta", "Advice": "Consigli",
    "Bluetooth devices": "Dispositivi Bluetooth", "Paired": "Associato", "Nearby": "Nelle vicinanze", "Distance": "Distanza",
    "Address": "Indirizzo", "Unnamed device": "Dispositivo senza nome", "Game controller": "Controller di gioco", "Phone": "Telefono",
    "Headphones": "Cuffie", "Speaker": "Altoparlante", "Smart light": "Luce smart", "Watch or wearable": "Orologio o indossabile",
    "Keyboard": "Tastiera", "Mouse": "Mouse", "Tracker": "Localizzatore", "Bluetooth device": "Dispositivo Bluetooth",
    "Interface": "Interfaccia", "Looking for interfaces…": "Ricerca delle interfacce…",
    "No adapter found: the default one is used": "Nessun adattatore trovato: si usa quello predefinito",
    "Windows always searches with its active Bluetooth adapter.": "Windows cerca sempre con l'adattatore Bluetooth attivo.",
    "very close (< 1 m)": "vicinissimo (< 1 m)", "near (1–3 m)": "vicino (1–3 m)", "in the room or next door": "nella stanza o accanto", "far": "lontano",
    // ---------- PCs, alerts, updates ----------
    "PCs": "PC", "PCs of the network": "PC della rete", "Health of the PCs of the network, read-only": "Salute dei PC della rete, in sola lettura",
    "Add a PC": "Aggiungi un PC", "Need attention": "Da controllare", "Unsafe programs": "Programmi insicuri", "This PC shares": "Questo PC condivide",
    "Share this PC": "Condividi questo PC", "Stop sharing": "Interrompi condivisione", "Create the key": "Crea la chiave", "Create a new key": "Crea una nuova chiave",
    "Allow it in the firewall": "Consentilo nel firewall", "Reachable": "Raggiungibile", "Not reachable": "Non raggiungibile",
    "Sharing key": "Chiave di condivisione", "Copy and close": "Copia e chiudi", "Port": "Porta", "Add": "Aggiungi",
    "PC name or IP address": "Nome del PC o indirizzo IP", "Search PCs…": "Cerca PC…", "No PC yet.": "Ancora nessun PC.", "Remove this PC": "Rimuovi questo PC",
    "Email and Telegram alerts": "Avvisi via email e Telegram", "Bot token": "Token del bot", "Chat ID": "ID della chat", "SMTP server": "Server SMTP",
    "User": "Utente", "Password": "Password", "Sender (optional)": "Mittente (facoltativo)", "Send to": "Invia a", "Send a test": "Invia una prova",
    "Forget the saved secrets": "Dimentica i segreti salvati", "A scheduled run failed": "Un'esecuzione pianificata non è riuscita",
    "The system drive is almost full": "Il disco di sistema è quasi pieno", "New unsafe programs were found": "Sono stati trovati nuovi programmi insicuri",
    "Program updates": "Aggiornamenti del programma", "Check now": "Controlla ora", "Install the update": "Installa l'aggiornamento", "Install": "Installa",
    "Alert settings saved.": "Impostazioni degli avvisi salvate.", "Search applications or publishers…": "Cerca applicazioni o editori…", "Search tasks…": "Cerca attività…"
  };
  // 2.6: search by symptom, before/after check, precise undo, network watch, router ports, Bluetooth trackers, Wi-Fi history.
  var IT_26 = {
    "Search a tool or describe the problem, e.g. Internet is slow… (press / )": "Cerca uno strumento o descrivi il problema, es. Internet lento… (premi / )",
    "Suggested for this problem": "Consigliato per questo problema", "Read first": "Prima leggi", "Then try": "Poi prova",
    "Run the reports": "Esegui i report", "Select the fixes": "Seleziona i fix",
    "Pick them in the selection bar, then run the ones the reports point to": "Li trovi nella barra di selezione: esegui quelli indicati dai report",
    "Fixes selected: read the reports, then run the ones you need from the selection bar.": "Fix selezionati: leggi i report, poi esegui quelli che servono dalla barra di selezione.",
    "Fixed": "Risolto", "Already fine": "Già a posto", "Applied": "Applicato", "Already set": "Già impostato", "Changed": "Cambiato",
    "Nothing changed": "Non è cambiato nulla", "Not fixed": "Non risolto", "Worse than before": "Peggio di prima", "Not verified": "Non verificato",
    "Undo": "Annulla", "Undone": "Annullato", "Verified": "Verifica", "Restore point…": "Punto di ripristino…",
    "The registry values this fix changed are put back exactly as they were before it ran. Nothing else on the PC changes: later fixes, programs and files stay as they are.":
      "I valori di registro modificati da questo fix tornano esattamente com'erano prima. Nient'altro cambia sul PC: fix successivi, programmi e file restano come sono.",
    "A restore point brings back the whole PC instead; it is still available from History.": "Un punto di ripristino invece riporta indietro tutto il PC; resta disponibile dalla Cronologia.",
    "Preview mode: nothing was put back.": "Modalità anteprima: non è stato ripristinato nulla.",
    "Ports the router opened to the internet (UPnP)": "Porte aperte dal router verso Internet (UPnP)", "Read the router": "Leggi il router",
    "Network watch": "Sorveglianza della rete", "Schedule it": "Pianificala", "Wi-Fi history": "Storico del Wi-Fi", "Schedule samples": "Pianifica le rilevazioni",
    "Record a sample every 15-30 minutes": "Registra una rilevazione ogni 15-30 minuti",
    "Unknown devices that keep showing up": "Dispositivi sconosciuti che continuano a comparire",
    "Unpaired devices seen in 3 or more scans over an hour are flagged as possibly following.": "I dispositivi non associati visti in 3 o più scansioni nell'arco di un'ora vengono segnalati come possibili inseguitori.",
    "Schedule Bluetooth scans": "Pianifica le scansioni Bluetooth", "to get an alert.": "per ricevere un avviso.",
    "May be following": "Potrebbe seguirti", "Seen": "Visto", "Mark as known": "Segna come noto",
    "Marked as known: it is no longer reported as following.": "Segnato come noto: non verrà più indicato come possibile inseguitore.",
    "Asking the router which ports it opened: a few seconds.": "Chiedo al router quali porte ha aperto: qualche secondo.",
    "Turn UPnP off on the router, or remove these forwards, unless you really need to reach the device from outside.":
      "Disattiva UPnP sul router, o rimuovi questi inoltri, a meno che tu non debba davvero raggiungere il dispositivo da fuori.",
    "No router answered the UPnP search: UPnP is off on the router (good), or this network blocks the search.":
      "Nessun router ha risposto alla ricerca UPnP: UPnP è spento sul router (bene) oppure questa rete blocca la ricerca.",
    "A UPnP device answered, but it exposes no port mapping service.": "Un dispositivo UPnP ha risposto, ma non espone il servizio di inoltro delle porte.",
    "UPnP is on, but no device opened a port right now.": "UPnP è attivo, ma in questo momento nessun dispositivo ha aperto porte.",
    "FTP sends passwords in clear text": "FTP invia le password in chiaro", "SSH is a constant target of password guessing": "SSH è un bersaglio continuo di tentativi sulle password",
    "Telnet has no encryption at all": "Telnet non ha alcuna crittografia",
    "a web admin page (cameras, NAS, printers) reachable from the internet": "una pagina di amministrazione (telecamere, NAS, stampanti) raggiungibile da Internet",
    "a web admin page reachable from the internet": "una pagina di amministrazione raggiungibile da Internet",
    "Windows file sharing (SMB): the way ransomware spreads": "condivisione file di Windows (SMB): la via con cui si diffonde il ransomware",
    "old Windows file sharing (NetBIOS)": "vecchia condivisione file di Windows (NetBIOS)", "a camera video stream (RTSP)": "il flusso video di una telecamera (RTSP)",
    "MQTT for smart-home devices, often without a password": "MQTT dei dispositivi domotici, spesso senza password",
    "Remote Desktop, the most attacked service on the internet": "Desktop remoto, il servizio più attaccato su Internet",
    "a NAS admin page (Synology DSM)": "la pagina di amministrazione di un NAS (Synology DSM)", "VNC remote control": "controllo remoto VNC",
    "a camera or DVR web page": "la pagina web di una telecamera o di un DVR", "a web admin page of a device": "la pagina di amministrazione di un dispositivo",
    "a device admin page": "la pagina di amministrazione di un dispositivo", "a Dahua camera or DVR": "una telecamera o un DVR Dahua",
    "a cheap DVR or camera (often with known flaws)": "un DVR o una telecamera economici (spesso con falle note)",
    "Samples": "Rilevazioni", "Weakest hour": "Ora più debole", "Channel or access point changes": "Cambi di canale o di access point",
    "Average signal by hour of the day (orange: below 50%)": "Segnale medio per ora del giorno (arancione: sotto il 50%)", "Latest changes": "Ultimi cambi",
    "From": "Da", "To": "A", "A new device joined the network": "Un nuovo dispositivo è entrato in rete",
    "Press": "Premi", "Schedule": "Pianifica",
    // The Toolbox page around the tools: help box, KPIs, filters, selection bar, cards.
    "Every tool in one place, by area. Fixes change the PC; reports only read it.": "Tutti gli strumenti in un posto, per area. I fix modificano il PC, i report lo leggono soltanto.",
    "Pick an area tab and switch between Fixes and Reports.": "Scegli un'area e passa tra Fix e Report.",
    "Run a tool, or tick several and press Run selected.": "Esegui uno strumento, oppure spuntane diversi e premi Esegui selezionati.",
    "Run diagnostics runs every report in the current view and opens their output.": "Esegui diagnostica avvia tutti i report della vista corrente e ne apre il risultato.",
    "Every maintenance tool in one place: find it, run it, schedule it or combine several": "Ogni strumento di manutenzione in un posto: trovalo, eseguilo, pianificalo o combinane diversi",
    "Run diagnostics": "Esegui diagnostica", "List": "Elenco", "Cards": "Schede", "Fixes": "Fix", "Fix": "Fix", "Tools": "Strumenti",
    "Read-only diagnostics": "Diagnostica in sola lettura", "Starred tools, shown first and on the dashboard": "Strumenti con la stella, mostrati per primi e nella dashboard",
    "Used this week": "Usati questa settimana", "Different tools run in 7 days": "Strumenti diversi eseguiti in 7 giorni", "All areas": "Tutte le aree",
    "Sort": "Ordina", "Shortest first": "Più brevi prima", "Recently run": "Eseguiti di recente", "Favorites only": "Solo preferiti", "Never run": "Mai eseguiti",
    "Search tools": "Cerca strumenti", "Clear": "Svuota", "Copy": "Copia", "Save as playbook": "Salva come sequenza", "Run selected": "Esegui selezionati",
    "No tool matches": "Nessuno strumento corrisponde", "Change the area, the filters or the search text.": "Cambia area, filtri o testo della ricerca.",
    "Details": "Dettagli", "Add to favorites": "Aggiungi ai preferiti", "Remove from favorites": "Togli dai preferiti", "Pin to the dashboard": "Fissa nella dashboard",
    "Last output": "Ultimo risultato", "Compact list or cards with descriptions": "Elenco compatto o schede con descrizione",
    "Run every read-only report in the current view": "Esegui tutti i report in sola lettura della vista corrente",
    "Names and IDs of the selected tools, for a ticket or a script": "Nomi e ID degli strumenti selezionati, per un ticket o uno script",
    "Keep the selection as one of My playbooks, to run it again with one click": "Conserva la selezione tra Le mie sequenze, per rieseguirla con un clic",
    "Fixes change a setting or delete files. Reports only read the PC and open their output when they finish.":
      "I fix cambiano un'impostazione o eliminano file. I report leggono soltanto il PC e mostrano il risultato quando finiscono.",
    "Safe tools run without asking. Moderate and high ones ask first and create a restore point.":
      "Gli strumenti sicuri partono senza chiedere. Quelli moderati e alti chiedono prima e creano un punto di ripristino.",
    "Changes a setting or deletes files": "Cambia un'impostazione o elimina file", "Read-only: changes nothing": "Sola lettura: non cambia nulla",
    "No favorites yet: press the star on a tool.": "Nessun preferito: premi la stella su uno strumento.",
    "Added to favorites: shown first here and on the dashboard.": "Aggiunto ai preferiti: compare per primo qui e nella dashboard.",
    "Removed from favorites.": "Tolto dai preferiti.", "Saved in Playbooks › My playbooks.": "Salvata in Sequenze › Le mie sequenze.",
    "e.g. Monthly visit at the office": "es. Visita mensile in ufficio",
    "No tool name contains these words: the suggestions above fit the problem you described.": "Nessun nome di strumento contiene queste parole: i suggerimenti qui sopra corrispondono al problema descritto.",
    ": it asks the router, through UPnP, which ports it opened to the internet and which device asked for each one. Cameras, NAS and consoles often do it by themselves. Nothing is changed.":
      ": chiede al router, tramite UPnP, quali porte ha aperto verso Internet e quale dispositivo le ha chieste. Telecamere, NAS e console lo fanno spesso da soli. Non viene modificato nulla.",
    "(for example every hour): each time it scans the network and sends an e-mail or Telegram alert when a device never seen before joins. Alerts are set in Settings › Alerts.":
      "(per esempio ogni ora): ogni volta scansiona la rete e invia un avviso via email o Telegram quando entra un dispositivo mai visto. Gli avvisi si impostano in Impostazioni › Avvisi.",
    "Every Wi-Fi scan records the signal, the channel and how crowded it is. Schedule": "Ogni scansione Wi-Fi registra segnale, canale e affollamento. Pianifica",
    "every 15-30 minutes: after a day you see whether the drops depend on the hour, on a neighbour changing channel or on the router.":
      "ogni 15-30 minuti: dopo un giorno vedi se le cadute dipendono dall'ora, da un vicino che cambia canale o dal router.",
    "A tracker (AirTag, Tile, SmartTag) hidden in a bag or a car behaves like this. If one is yours or a neighbour's, mark it as known.":
      "Un localizzatore (AirTag, Tile, SmartTag) nascosto in una borsa o in un'auto si comporta così. Se è tuo o di un vicino, segnalo come noto.",
    "An unknown Bluetooth tracker keeps showing up": "Un localizzatore Bluetooth sconosciuto continua a comparire"
  };
  Object.keys(IT_26).forEach(function (k) { if (!Object.prototype.hasOwnProperty.call(IT, k)) IT[k] = IT_26[k]; });
  // The 351 Toolbox tools (names, descriptions, warnings) live in i18n_tools.js; the console's own phrases win on a clash.
  Object.keys(window.I18N_TOOLS || {}).forEach(function (k) { if (!Object.prototype.hasOwnProperty.call(IT, k)) IT[k] = window.I18N_TOOLS[k]; });
  // The pages outside the Toolbox (2.7) live in i18n_pages.js.
  Object.keys(window.I18N_PAGES || {}).forEach(function (k) { if (!Object.prototype.hasOwnProperty.call(IT, k)) IT[k] = window.I18N_PAGES[k]; });

  // Dynamic text: [pattern, replacement or function]. Applied when the exact phrase is not in the dictionary.
  var MONTHS = { Jan: "gen", Feb: "feb", Mar: "mar", Apr: "apr", May: "mag", Jun: "giu", Jul: "lug", Aug: "ago", Sep: "set", Oct: "ott", Nov: "nov", Dec: "dic" };
  var RULES = [
    // 2.6: precise undo, router ports, Bluetooth sightings, Wi-Fi history.
    [/^Put back only the (\d+) registry values this fix changed$/, "Ripristina solo i $1 valori di registro modificati da questo fix"],
    [/^(\d+) of (\d+) values put back(?:; (\d+) could not be changed)?\.$/, function (m, a, b, c) {
      return a + " di " + b + " valori ripristinati" + (c ? "; " + c + " non modificabili" : "") + ".";
    }],
    [/^Undo (.+)$/, function (m, what) { return "Annulla " + (translate(what) || what); }],
    [/^(\d+) ports opened through UPnP, (\d+) worth closing\.$/, "$1 porte aperte tramite UPnP, $2 da chiudere."],
    [/^No router answered with a port mapping service: UPnP looks off on the router \(good\)\. Only other devices answered: (.+)\.$/,
      "Nessun router ha risposto con il servizio di inoltro delle porte: UPnP sembra spento sul router (bene). Hanno risposto solo altri dispositivi: $1."],
    [/^scanned ([A-Z][a-z]{2} \d{1,2}, \d{4}.*)$/, function (m, when) { return "scansione del " + (translate(when) || when); }],
    [/^(\d+) scans$/, "$1 scansioni"], [/^over (\d+) min$/, "in $1 min"], [/^(\d+) samples so far\.$/, "$1 rilevazioni finora."],
    [/^average signal (.+)$/, "segnale medio $1"],
    // The Toolbox counters and the per-tool labels ("Select Flush DNS", "Schedule Flush DNS").
    [/^(\d+) of (\d+) tools$/, "$1 di $2 strumenti"], [/^(\d+) tools$/, "$1 strumenti"], [/^(\d+) areas$/, "$1 aree"],
    [/^(\d+) safe, the others ask first$/, "$1 sicuri, gli altri chiedono prima"], [/^(\d+) read-only reports in the current view$/, "$1 report in sola lettura nella vista corrente"],
    [/^(\d+) tools: (\d+) fixes and (\d+) read-only reports$/, "$1 strumenti: $2 fix e $3 report in sola lettura"],
    [/^(\d+) selected$/, "$1 selezionati"], [/^(\d+) ask first$/, "$1 chiedono prima"],
    [/^(\d+) tools, in a safe order\. It appears in Playbooks › My playbooks\.$/, "$1 strumenti, in un ordine sicuro. Compare in Sequenze › Le mie sequenze."],
    [/^(Select|Schedule|Run) (.+)$/, function (m, verb, what) {
      var t = translate(what);
      return t == null ? m : { Select: "Seleziona ", Schedule: "Pianifica ", Run: "Esegui " }[verb] + t;
    }],
    [/^All of (.+)$/, function (m, what) { var t = translate(what); return t == null ? m : "Tutto in " + t; }],
    [/^(Open|More in|Hide the pages of) (.+)$/, function (m, verb, what) {
      var t = translate(what);
      return t == null ? m : { "Open": "Apri ", "More in": "Altro in ", "Hide the pages of": "Nascondi le pagine di " }[verb] + t;
    }],
    [/^Run (.+) again$/, function (m, what) { var t = translate(what); return t == null ? m : "Esegui di nuovo " + t; }],
    // Numbers in the middle of page texts (2.7).
    [/^(.+) score: (\d+) of 100$/, function (m, what, n) { var t = translate(what); return t == null ? m : "Punteggio " + t + ": " + n + " su 100"; }],
    [/^Overall health: (\d+) of 100$/, "Salute generale: $1 su 100"],
    [/^(\d+) fixes match what this PC shows now: run them in this order\.$/, "$1 fix corrispondono a ciò che mostra ora questo PC: eseguili in questo ordine."],
    [/^(\d+) ports opened through UPnP, (\d+) worth closing\.$/, "$1 porte aperte tramite UPnP, $2 da chiudere."],
    [/^Only minor improvements are suggested\. (\d+) of (\d+) areas assessed\.$/, "Sono suggeriti solo piccoli miglioramenti. $1 aree valutate su $2."],
    [/^(\d+) of (\d+) assessed ·$/, "$1 su $2 valutate ·"], [/^([\d.,]+) of ([\d.,]+) GB in use$/, "$1 di $2 GB in uso"],
    [/^([\d.,]+) of ([\d.,]+) GB · commit (\d+)%$/, "$1 di $2 GB · impegnata $3%"], [/^In (.+) · Out (.+)$/, "In entrata $1 · In uscita $2"],
    [/^View all (\d+)$/, "Vedi tutti ($1)"], [/^Open the (\d+) improvement\(s\) of this area$/, "Apri i $1 miglioramenti di quest'area"],
    [/^Show dismissed and snoozed \((\d+)\)$/, "Mostra nascosti e rinviati ($1)"], [/^Last quick scan (\d+) days ago$/, "Ultima analisi rapida $1 giorni fa"],
    [/^(\d+) stability events in the last 30 days\.$/, "$1 eventi di stabilità negli ultimi 30 giorni."], [/^(\d+) actions recorded on this device\.$/, "$1 azioni registrate su questo dispositivo."],
    [/^(\d+) updates are waiting\.$/, "$1 aggiornamenti in attesa."], [/^(\d+) programs start with Windows\. Turn off the ones you do not need in the list below\.$/,
      "$1 programmi partono con Windows. Disattiva quelli che non ti servono nell'elenco qui sotto."],
    [/^(\d+) programs start with Windows\. Disable unneeded ones in Task Manager > Startup apps\.$/, "$1 programmi partono con Windows. Disattiva quelli superflui in Gestione attività > App di avvio."],
    [/^Drive C: has (\d+)% free: the component store can usually shrink by several GB\.$/, "L'unità C: ha il $1% libero: di solito l'archivio componenti può ridursi di diversi GB."],
    [/^Browser caches use (.+)\.$/, "Le cache dei browser occupano $1."], [/^hiberfil\.sys uses (.+) on this desktop PC\.$/, "hiberfil.sys occupa $1 su questo PC desktop."],
    [/^The firmware is (\d+) years old\.$/, "Il firmware ha $1 anni."], [/^Not updated since (\d{4}): check whether a newer version exists\.$/, "Non aggiornato dal $1: controlla se esiste una versione più recente."],
    [/^(\d+) third-party drivers are older than 3 years \(e\.g\. (.+)\)\.$/, "$1 driver di terze parti hanno più di 3 anni (es. $2)."],
    [/^(\d+) PCs of the network · (\d+) reachable$/, "$1 PC della rete · $2 raggiungibili"], [/^(\d+) of (\d+) others reachable$/, "$1 di $2 altri raggiungibili"],
    [/^(.+) \(this PC\)$/, "$1 (questo PC)"], [/^At every startup, after (\d+) min$/, "A ogni avvio, dopo $1 min"], [/^At every sign-in, after (\d+) min$/, "A ogni accesso, dopo $1 min"],
    [/^Peak in view (\d+)%$/, "Picco nella vista $1%"], [/^In use: (.+)$/, "In uso: $1"], [/^Not used: (.+)$/, "Non usati: $1"], [/^of (\d+) installed$/, "su $1 installati"],
    [/^(\d+) safe, no confirmation$/, "$1 sicuri, senza conferma"], [/^(\d+) not readable$/, "$1 non leggibili"], [/^(\d+) run\(s\), (\d+) scan\(s\)$/, "$1 esecuzioni, $2 scansioni"],
    [/^(\d+) service\(s\) in the restore backup$/, "$1 servizi nel backup di ripristino"], [/^(\d+) cleanup run\(s\)$/, "$1 pulizie eseguite"],
    [/^(\d+) actions between the two dates · (.+) freed\.$/, "$1 azioni tra le due date · $2 liberati."], [/^Nothing planned in the next 7 days\.$/, "Nulla in programma nei prossimi 7 giorni."],
    [/^Hide it for 7 days, then show it again$/, "Nascondilo per 7 giorni, poi mostralo di nuovo"],
    [/^Updated (.+) · oldest area scan (.+)$/, function (m, a, b) { return "Aggiornato " + a + " · scansione più vecchia " + (translate(b) || b); }],
    [/^Last check (.+) · baseline from (.+)$/, function (m, a, b) { return "Ultimo controllo " + (translate(a) || a) + " · riferimento del " + (translate(b) || b); }],
    [/^last reading (.+)$/, function (m, a) { return "ultima rilevazione " + (translate(a) || a); }], [/^since (.+)$/, function (m, a) { return "dal " + (translate(a) || a); }],
    [/^Last run (.+)$/, function (m, a) { return "Ultima esecuzione " + (translate(a) || a); }],
    [/^(\d+):00 · signal (.+) · (\d+) samples · (.+) networks on the same channel$/, "$1:00 · segnale $2 · $3 rilevazioni · $4 reti sullo stesso canale"],
    [/^(\d+) devices compared with (\d+) vulnerabilities · CISA catalog (.*)$/, "$1 dispositivi confrontati con $2 vulnerabilità · catalogo CISA $3"],
    [/^(\d+) daily readings since (.+)$/, function (m, n, a) { return n + " rilevazioni giornaliere dal " + (translate(a) || a); }],
    [/^(.+) \(preview: nothing changed\)$/, function (m, what) { return (translate(what) || what) + " (anteprima: nulla è cambiato)"; }],
    [/^Restart in (\d+) minute\(s\)$/, "Riavvio tra $1 minuti"], [/^Shut down in (\d+) minute\(s\)$/, "Arresto tra $1 minuti"],
    [/^Clear the (.+) cache$/, "Svuota la cache di $1"], [/^Start the uninstaller of (.+)$/, "Avvia il programma di disinstallazione di $1"],
    [/^Remove (.+) \(preview: nothing changed\)$/, function (m, what) { return "Rimuovi " + what + " (anteprima: nulla è cambiato)"; }],
    // The interface choices of the network scanner: "Wi-Fi · 192.168.1.0/24 · gateway 192.168.1.1 (active)".
    [/^(?=.*(?:\(active\)$| · no gateway| · connected to | · not connected| · off$))(.*)$/, function (m, all) {
      return all.replace(/ \(active\)$/, " (attiva)").replace(" · no gateway", " · senza gateway").replace(" · connected to a network", " · connessa a una rete")
        .replace(" · connected to ", " · connessa a ").replace(" · not connected", " · non connessa").replace(/ · off$/, " · spento");
    }],
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
