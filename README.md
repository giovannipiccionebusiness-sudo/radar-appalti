# Radar Appalti GitHub — versione completa 2.0

## Funzioni
- GitHub Pages, utilizzabile anche da smartphone.
- Due scansioni automatiche nei giorni lavorativi e una ogni giorno.
- Oltre 20 fonti nazionali, europee e regionali.
- ANAC, TED, Acquisti in Rete PA, EmPULIA, CUC Terra di Leuca e principali centrali regionali.
- Ampio elenco CPV e parole chiave.
- Esclusione di forniture non pertinenti e gare scadute.
- Lettura delle pagine di dettaglio quando la pagina elenco non basta.
- Punteggio automatico di priorità.
- Filtri per testo, categoria, regione e stato.
- Preferiti e stato salvati sul dispositivo.
- Esportazione CSV e archivio JSON.
- Stato tecnico di ogni fonte.
- Notifiche Telegram o email opzionali.

## Installazione
1. Crea un repository GitHub chiamato `radar-appalti`.
2. Estrai lo ZIP e carica tutto, inclusa `.github`.
3. Vai in `Settings → Pages`.
4. Scegli `Deploy from a branch`, branch `main`, cartella `/ (root)`.
5. Vai in `Actions → Scansione bandi → Run workflow`.
6. Apri `https://TUO-UTENTE.github.io/radar-appalti/`.

## Notifiche Telegram opzionali
Nel repository vai in `Settings → Secrets and variables → Actions` e crea:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Notifiche email opzionali
Crea questi secrets:
- `SMTP_HOST`
- `SMTP_PORT` (normalmente 465)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `ALERT_EMAIL`

Per Gmail serve una password per le app, non la password ordinaria.

## Modificare fonti, parole chiave e CPV
Apri `config.json`. Ogni fonte può essere attivata o disattivata con `"active": true/false`.

## Limite tecnico
Le piattaforme con login, CAPTCHA, protezioni anti-bot o contenuti caricati solo via JavaScript possono risultare non leggibili. La sezione “Stato delle fonti” indica subito quali collegamenti funzionano. ANAC rimane la fonte nazionale più importante.
