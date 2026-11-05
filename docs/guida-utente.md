# Windows Maintenance Manager — Guida per l'utente

Questa guida spiega come usare la console per tenere in forma un PC, senza conoscenze tecniche. Per l'installazione in azienda, i ruoli e il server centrale c'è il [manuale dell'amministratore](manuale-amministratore.md).

## Aprire la console

Fai doppio clic su **Windows Maintenance Manager** nel menu Start: la console si apre nel browser. Tutto resta sul tuo PC: niente viene inviato fuori, a meno che non lo attivi tu (avvisi, aggiornamenti, server centrale).

Se in azienda gli account sono attivi, accedi con il tuo nome utente e la password, oppure con "Accedi con l'account aziendale". Alcune pagine e alcuni strumenti potrebbero non esserci: dipende dal ruolo che ti è stato dato.

## Le sezioni

| Sezione | Pagine | Cosa ci trovi |
|---|---|---|
| **Panoramica** | Dashboard, Consigli | Lo stato del PC in un colpo d'occhio e le cose da sistemare prima, ordinate per effetto. |
| **Ottimizza** | Prestazioni, Pulizia, Archiviazione, Avvio e app, Applicazioni | PC più veloce, più spazio libero, meno programmi all'avvio. |
| **Salute** | Servizi, Integrità del sistema, Sicurezza, Aggiornamenti e driver, Rete, Hardware | Errori di Windows, protezione, aggiornamenti mancanti, dischi e temperature. |
| **Sistema** | Visualizzatore eventi, Gestione attività, Registro, Scanner di rete, Cassetta degli attrezzi | Strumenti per chi vuole guardare più a fondo. |
| **Operazioni** | Attività, Playbook, Pianificazioni, PC, Centro aziendale, Script, Cronologia, Report | Cosa è stato fatto, cosa è programmato, gli altri PC. |
| **Aiuto e impostazioni** | Supporto, Impostazioni, Utenti e ruoli | Assistenza, preferenze, account. |

## Il percorso più semplice

1. **Dashboard › Scansiona tutto.** In circa un minuto ogni area riceve un punteggio da 0 a 100.
2. **Consigli.** Ogni voce dice cosa cambia e quanto è rischiosa:
   - **sicuro:** si può sempre fare;
   - **moderato:** cambia un'impostazione;
   - **alto:** tocca parti delicate e chiede una conferma.
3. Premi **Esegui** su quello che ti interessa. Prima di una modifica l'app crea un punto di ripristino di Windows, e ogni modifica si può annullare dalla **Cronologia**.

## Tornare indietro

- **Cronologia:** per ogni esecuzione mostra cosa è cambiato e, dove possibile, il pulsante **Annulla**, che rimette i valori di prima.
- **Sicurezza › Punti di ripristino:** riporta Windows a un punto di ripristino.

## Farlo in automatico

- **Pianificazioni:** scegli uno strumento, per esempio la pulizia dei file temporanei, e quando eseguirlo: ogni giorno, ogni settimana, all'avvio o all'accesso. Le pianificazioni funzionano anche con la console chiusa.
- **Playbook:** più strumenti in fila, per esempio una "manutenzione del venerdì".

## Avvisi

Impostazioni › Avvisi manda un messaggio quando qualcosa non va, per esempio un disco quasi pieno, la protezione spenta o errori gravi. I canali sono email, Telegram o webhook; puoi scegliere quali avvisi ricevere e le ore di silenzio.

## Report

In Report scegli il report e scaricalo in HTML o PDF. Nel Centro aziendale c'è anche il **report per la direzione**: un PDF con salute, lavoro fatto, incidenti e conformità.

## Domande frequenti

**L'app può rompere Windows?**
Gli strumenti ad alto rischio chiedono conferma e spesso l'amministratore li blocca. Prima di ogni modifica c'è un punto di ripristino, e quasi tutto si annulla dalla Cronologia.

**Cosa vuol dire "Il tuo ruolo non lo consente"?**
Il tuo account non ha quel permesso: chiedilo all'amministratore. Il tentativo viene comunque registrato nel registro di controllo.

**Uno strumento dice "Serve l'approvazione".**
In azienda alcuni strumenti richiedono il sì di una seconda persona. La richiesta è già stata inviata: lo strumento parte quando viene approvata.

**La console non si apre.**
Avvia di nuovo l'app dal menu Start. Se la porta 8765 è occupata, l'app ne usa un'altra. La porta si cambia in Impostazioni › App.
