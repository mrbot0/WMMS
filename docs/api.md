# API della console

La descrizione completa è in [openapi.json](openapi.json) (OpenAPI 3.1). Il file è generato dalla tabella delle rotte con `tools/build_docs.py`, quindi corrisponde sempre al codice, e i test controllano che sia aggiornato. Ogni console la serve anche da `GET /api/v1/openapi.json`.

Per ogni operazione, il campo `x-permissions` dice quali permessi servono quando gli account sono attivi: il ruolo dell'utente, o gli ambiti del token, deve averli tutti.

## Autenticazione

| Situazione | Cosa inviare |
|---|---|
| Account spenti | L'intestazione `X-WMM-Token` della console, per ogni scrittura. |
| Account attivi, un utente | `X-WMM-Session` (la restituisce `POST /api/v1/auth/login`) e, per le scritture, `X-WMM-Token`. |
| Account attivi, uno script | `Authorization: Bearer wmm_…`, con un token creato in Impostazioni › Token API. Sostituisce entrambe le intestazioni. |

## Esempio (PowerShell)

```powershell
$h = @{ Authorization = "Bearer wmm_xxxxxxxxxxxxxxxx" }
Invoke-RestMethod http://127.0.0.1:8765/api/v1/dashboard -Headers $h
Invoke-RestMethod http://127.0.0.1:8765/api/v1/runs -Method Post -Headers $h -ContentType application/json `
  -Body '{"actions": ["network.flush_dns"], "reason": "TICKET-42"}'
```

Il modulo `tools/WMM.psm1` ha gli stessi comandi già pronti, tra cui `Connect-Wmm`, `Get-WmmHealth`, `Start-WmmRun`, `Get-WmmHistory`, `Get-WmmAudit`, `Get-WmmCentralPc` e `Send-WmmCentralJob`.

## Risposte

| Codice | Significato |
|---|---|
| `200`, `201` | Fatto. |
| `202` | Esecuzione avviata, oppure richiesta di approvazione inviata (campo `approval`). |
| `400` | Dati non validi; il messaggio dice quali. |
| `401` | Manca l'accesso, oppure il token non è valido. |
| `403` | Il ruolo non ha il permesso; il messaggio elenca i permessi che mancano. |
| `409` | Non si può fare adesso: per esempio c'è un'altra esecuzione in corso, lo strumento è bloccato o serve un'approvazione. |
