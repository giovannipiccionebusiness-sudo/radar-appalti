# Radar Appalti GitHub 4.0

Questa versione sostituisce la 3.0 ed è stata riscritta per evitare il blocco del workflow.

## Principali correzioni

- Scansione delle fonti in parallelo.
- Timeout brevi per connessione e lettura.
- Una fonte lenta non blocca le altre.
- Timeout massimo del workflow ridotto a 12 minuti.
- Parser dedicato per la pagina ANAC Pubblicità legale.
- Collegamento diretto alla Search API ufficiale TED.
- Numero limitato di pagine di dettaglio per ogni fonte.
- Conservazione delle gare precedenti quando una fonte è temporaneamente offline.
- Tempi di risposta visibili nel riquadro “Stato delle fonti”.
- Verifica automatica della sintassi prima della scansione.
- File CSV e JSON aggiornati nello stesso workflow.

## Aggiornamento del repository

1. Estrai lo ZIP.
2. Carica tutti i file nel repository, sostituendo quelli esistenti.
3. Controlla che venga caricata anche la cartella `.github`.
4. Vai in `Actions`.
5. Apri `Scansione bandi v4`.
6. Premi `Run workflow`.

## Tempo previsto

Normalmente la scansione dovrebbe concludersi in circa 1–4 minuti. I portali temporaneamente irraggiungibili vengono registrati come errore senza interrompere il resto.

## TED

La versione 4 usa l’endpoint ufficiale:

`POST https://api.ted.europa.eu/v3/notices/search`

L’API non richiede autenticazione. Qualora il formato della risposta TED venga modificato, il radar segnalerà l’errore ma continuerà a elaborare tutte le altre fonti.

## Notifiche facoltative

Per Telegram:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Per email:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `ALERT_EMAIL`

I valori si inseriscono in:

`Settings → Secrets and variables → Actions`
