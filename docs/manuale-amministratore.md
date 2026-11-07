# Windows Maintenance Manager — Manuale dell'amministratore

Versione 2.12. Questo manuale spiega come installare l'app in azienda, accendere gli account e i ruoli, collegare l'accesso aziendale (Microsoft Entra ID o Active Directory), usare il server centrale (anche con più clienti) e spostarlo su un altro PC.

## 1. Requisiti

- Windows 10 o 11, 64 bit.
- Python 3.12 installato **per tutti gli utenti** (installer di python.org, opzione "Install for all users"). L'MSI lo cerca in `HKLM\SOFTWARE\Python\PythonCore\3.12`.
- Per le pianificazioni e l'agente in background: l'app installata in `C:\Program Files\Windows Maintenance Manager` (lo fa l'MSI o `wmm.py --install`).

## 2. Installazione

### 2.1 Un solo PC

Avviare `wmm.py` (o il setup `WindowsMaintenanceManager-Setup-<versione>.exe`). La console si apre nel browser su `http://127.0.0.1:8765`.

### 2.2 Molti PC: MSI con Criteri di gruppo o Intune

Ogni release su GitHub contiene `WindowsMaintenanceManager-<versione>.msi`. È costruito da GitHub Actions e firmato quando il repository ha il certificato (secret `WMM_SIGN_PFX_BASE64` e `WMM_SIGN_PASSWORD`). Il suo SHA-256 è in `SHA256SUMS.txt`.

Installazione silenziosa:

```
msiexec /i WindowsMaintenanceManager-2.12.0.msi /qn CONFIG="\\server\share\wmm-config.json" BACKGROUND=1
```

| Proprietà | Significato |
|---|---|
| `CONFIG` | Un backup della configurazione (Impostazioni › Dati › Scarica un backup). Può contenere `central_code` per iscrivere subito il PC al server centrale. |
| `BACKGROUND=1` | Installa l'agente in background (attività pianificata come SYSTEM): pianificazioni, avvisi e server centrale funzionano anche senza la console aperta. |

- **Intune:** caricare l'MSI come "Line-of-business app" con gli stessi argomenti.
- **Criteri di gruppo:** usare "Installazione software", oppure uno script di avvio con la riga sopra.

### 2.3 Aggiornamenti

Impostazioni › Aggiornamenti controlla le release su GitHub.

- **Copia installata con l'MSI:** si aggiorna con il nuovo MSI, così Windows Installer continua a sapere cosa è installato (riparazione, disinstallazione, inventario). Il pacchetto si installa solo se corrisponde al suo SHA-256 e, quando è firmato, se la firma è valida.
- **Altre copie:** si aggiornano con lo zip, anch'esso controllato con il suo SHA-256.

I dati in `dati\` non vengono mai toccati.

## 3. Account, ruoli e permessi

Gli account sono spenti di default: chi apre la console sul PC la usa senza accesso. Per accenderli: Impostazioni › Account › Attiva gli account. Il primo utente creato è l'Amministratore.

### 3.1 Ruoli predefiniti

| Ruolo | Cosa può fare |
|---|---|
| Amministratore | Tutto, compresi utenti, ruoli e criteri di sicurezza. Non modificabile. |
| Tecnico | Tutte le pagine e gli strumenti, pianificazioni, script, registro e altri PC; niente utenti, ruoli o criteri. |
| Operatore | Scansioni, report e correzioni sicure nelle pagine delle aree. |
| Visualizzatore | Vede lo stato del PC e i report; esegue solo report in sola lettura. |
| Revisore | Cronologia, report, utenti e registro di controllo, in sola lettura. |

Nella pagina **Utenti e ruoli** si creano ruoli nuovi, anche copiando un ruolo esistente, e si sceglie permesso per permesso:

- cosa il ruolo **vede** (`view.<pagina>`);
- cosa **esegue** (`run.<area>.<rischio>`: report, sicuro, moderato o alto per ogni area);
- cosa **gestisce** (per esempio `users.manage`, `central.manage`, `approvals.decide`).

Nessuno può dare a un ruolo permessi che non ha lui stesso.

### 3.2 Controlli che valgono per tutti

- **Regole delle esecuzioni** (Impostazioni › Esecuzioni): blocco degli strumenti ad alto rischio, motivo o numero di ticket obbligatorio, conferma con il nome del PC.
- **Approvazioni:** uno strumento a rischio chiede il sì di una seconda persona che ha `approvals.decide`.
- **Registro di controllo:** ogni modifica finisce qui. Il registro è a catena di hash: una riga cambiata o tolta si vede in "Verifica". Si può inoltrare a un SIEM (syslog) o a un webhook.

### 3.3 Verifica automatica dei permessi

Ad ogni modifica del codice, i test (`tests/test_v211.py`) chiamano tutte le rotte dell'API in tre modi:

- senza sessione;
- con un ruolo senza permessi;
- con un ruolo che ha tutti i permessi tranne quelli richiesti dalla rotta.

Tutte e tre le chiamate devono essere rifiutate. Una rotta nuova senza permesso dichiarato richiede quelli dell'amministratore.

## 4. Accesso con gli account aziendali

### 4.1 Microsoft Entra ID, passo per passo

1. Nel portale Entra apri **App registrations › New registration**. Nome: `Windows Maintenance Manager`. Account supportati: *solo questa organizzazione*.
2. **Redirect URI:** piattaforma *Public client/native (mobile & desktop)*, indirizzo `http://127.0.0.1:8765/api/v1/auth/oidc/callback`. Se hai cambiato la porta della console, usa quella.
3. In **Authentication** lascia attivo "Allow public client flows". Non serve un client secret: l'app usa PKCE.
4. In **Token configuration › Add groups claim** scegli *Security groups*. In alternativa puoi usare gli **App roles** e il claim `roles`.
5. Copia l'**Application (client) ID** e il **Directory (tenant) ID**.
6. Nella console apri Impostazioni › Accesso aziendale e compila i campi:

   | Campo | Valore |
   |---|---|
   | Issuer | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
   | Client ID | l'Application ID |
   | Claim del ruolo | `groups` (o `roles`) |
   | Mappa dei ruoli | l'ID di ogni gruppo Entra → il ruolo dell'app |
   | Ruolo predefinito | vuoto, così chi non è in un gruppo mappato viene rifiutato |
   | Domini ammessi | facoltativo, per esempio `azienda.it` |

   Gli issuer `common` e `organizations` vengono rifiutati, perché accetterebbero account di qualunque organizzazione.
7. Prova con "Accedi con l'account aziendale" dalla schermata di accesso.

L'app controlla issuer, audience, scadenza e nonce del token. Il ruolo viene ricalcolato a ogni accesso.

### 4.2 Windows / Active Directory

Impostazioni › Accesso aziendale › Account Windows. La password la verifica Windows stesso e non viene mai salvata. Il ruolo viene dai gruppi Windows dell'account, secondo la mappa (per esempio `AZIENDA\Help Desk` → Tecnico).

## 5. Token per script e integrazioni

Impostazioni › Token API crea un token `wmm_…`, mostrato una sola volta. Il token ha solo gli ambiti scelti; senza ambiti, ha i permessi attuali dell'utente. Un token non può accedere, cambiare password o gestire altri token.

L'elenco completo delle rotte, con i permessi richiesti, è nella descrizione OpenAPI: vedi [api.md](api.md).

## 6. Server centrale

Un PC fa da server; gli altri lo chiamano via HTTPS, anche da altre sedi e fuori ufficio, dietro NAT.

1. Centro aziendale › PC gestiti › **Server centrale attivo**. Usa la porta 8770 e un certificato creato sul PC, di cui viene mostrata l'impronta SHA-256.
2. Crea un **codice di iscrizione**: indirizzo del server, gruppi ed eventualmente il cliente (vedi §7). Il codice vale 24 ore e una sola volta.
3. Su ogni PC, in Centro aziendale › Questo PC, incolla il codice. Il PC fissa l'impronta del certificato e da quel momento accetta solo quel server.
4. Su ogni PC scegli cosa il server può eseguire lì: solo report, report e correzioni sicure, oppure tutto. La decisione è del PC, non del server.

Dal server si inviano lavori: strumenti, software (winget), anelli di Windows Update, baseline di conformità e inventario.

## 7. Più clienti (fornitori di servizi)

Per chi gestisce i PC di più aziende: Centro aziendale › **Clienti**.

- Ogni PC appartiene a un cliente, oppure a nessuno. Il cliente si sceglie nel codice di iscrizione o con "Aggiungi PC".
- **Chi vede quali clienti:** un tecnico limitato a uno o più clienti vede e gestisce solo i loro PC, lavori, inventario ed export. Chi non ha clienti assegnati vede tutto (è lo staff del fornitore).
- Alcune cose valgono per tutti i clienti, quindi un tecnico limitato non può cambiarle: impostazioni del server, gruppi, catalogo software, anelli, backup e spostamento.

## 8. Backup e spostamento del server centrale

Centro aziendale › **Backup e spostamento**. I passi sono tre.

1. **Indica ai PC il nuovo indirizzo:** nome o IP e porta del nuovo server. I PC lo useranno dal contatto successivo. Il certificato resta lo stesso, quindi accettano solo un server che ha il certificato del backup.
2. **Fai il backup:** un file `.wmmcentral` cifrato con una password di almeno 12 caratteri (PBKDF2-SHA256 con 300.000 iterazioni e sigillo HMAC).
   - Contiene PC, lavori, gruppi, asset, catalogo, anelli, clienti, il certificato e la sua chiave.
   - I segreti dei PC, che sul server sono cifrati per l'utente Windows (DPAPI), sono in chiaro solo dentro il file cifrato.
3. **Ripristina sul nuovo PC:** scegli il file e scrivi la password. Prima di toccare qualcosa, l'app mostra cosa contiene: PC, clienti e impronta. Poi il server centrale di quel PC viene sostituito; la copia precedente resta in `dati\db-backups` e `dati\tls\previous-*`.

I PC **non vanno iscritti di nuovo**. Un PC rimasto spento durante lo spostamento continua a chiamare il vecchio indirizzo finché non riceve il nuovo, o finché non viene iscritto di nuovo.

## 9. Database e migrazioni

I database `dati\wmm.db`, `dati\accounts.db` e `dati\central.db` hanno una versione (`PRAGMA user_version`). All'avvio di una versione nuova dell'app:

1. il database viene copiato in `dati\db-backups` (restano le ultime 5 copie);
2. i passi mancanti vengono applicati in una sola transazione: se uno fallisce, il database resta com'era.

Un database scritto da una versione più recente dell'app non viene modificato. Le versioni e le copie si vedono in Impostazioni › Dati.

## 10. Novità 2.12 per l'amministratore

- **Impostazioni › Panoramica**: lo stato di account, avvisi, installazione, regole delle esecuzioni, cifratura, aggiornamenti, backup e automazione, con il link a ogni sezione.
- **Automazione**:
  - regole "quando succede questo, avvia uno strumento": solo strumenti sicuri, al massimo una volta ogni 30 minuti;
  - obiettivi con l'avviso *Obiettivo non rispettato*;
  - programmi che winget non deve aggiornare.
- **Backup dei tuoi file**: copia su un altro disco o su un NAS (strumento *Copia i tuoi file su un disco o un NAS*, da pianificare ogni giorno). Non cancella mai nulla nella destinazione.
- **Utenti e ruoli**:
  - ruoli temporanei che tornano da soli al ruolo precedente;
  - **revisione degli accessi**, registrata nel registro di controllo con "Segna come rivisto".
- **Centro aziendale**:
  - **campagne** con scadenza e avanzamento, con le stesse regole dei lavori (rischio, approvazioni, motivo);
  - i PC che richiedono attenzione per primi.
- **Pianificazioni quando il PC è inattivo**: si avviano dopo 10 minuti senza uso, o dopo l'attesa scelta.

## 11. Novità 2.13: backup in Archiviazione

Archiviazione ha la scheda **Backup**. Ogni backup salva le cartelle scelte (con i nomi da saltare) su un altro disco o una condivisione NAS,
nella cartella `<destinazione>\<nome del PC>\<nome del backup>`:

| Tipo | Cosa fa |
|---|---|
| Copia | copia i file nuovi e modificati; nella destinazione non cancella nulla (robocopy /E) |
| Mirror | la destinazione diventa una copia esatta, cancellazioni comprese (robocopy /MIR) |
| Archivi datati | uno zip per esecuzione con il manifest; tiene le ultime N versioni; cifratura facoltativa con password |

- La password degli archivi è protetta con DPAPI per la macchina, così le esecuzioni pianificate (SYSTEM) possono usarla. **Senza la password un archivio cifrato non si apre.**
- Le versioni si sfogliano, si verificano (ogni file riletto e controllato) e si ripristinano: tutte o solo i file scelti, in una nuova cartella o al loro posto, mantenendo o sostituendo i file presenti. *Prova* mostra cosa succederebbe senza scrivere nulla.
- I backup giornalieri e settimanali partono con lo strumento *Esegui i backup in scadenza*: pianificalo ogni ora o quando il PC è inattivo.
- Permessi: leggere richiede `view.storage`; eseguire ed eliminare un backup `run.storage.safe`; crearlo o modificarlo, ripristinare in una nuova cartella ed eliminare una versione `run.storage.moderate`; sostituire file o ripristinarli al loro posto `run.storage.high`.
- Windows, i programmi, ProgramData e i dati di WMM sono rifiutati come sorgente, destinazione e cartella di ripristino: l'agente ha più diritti di chi usa la console.
- Dati: `dati\backups.json` (profili) e `dati\backup_history.json` (ultime 500 esecuzioni).

## 12. Dove sono i dati

| Cosa | Dove |
|---|---|
| Cronologia, pianificazioni | `dati\wmm.db` |
| Utenti, ruoli, sessioni, registro di controllo, token, approvazioni | `dati\accounts.db` |
| Server centrale | `dati\central.db`, `dati\tls\` (solo amministratori) |
| PC iscritto al server | `dati\central_client.json` (segreto cifrato DPAPI) |
| Copie prima delle migrazioni | `dati\db-backups\` |
| Impostazioni | `dati\app_settings.json`; accesso aziendale, integrazioni e server centrale in `dati\integrations.json` |
