# Radar Appalti GitHub 5.0 – Consip

La versione 5.0 aggiunge il monitoraggio dedicato delle opportunità Consip.

## Fonti Consip controllate

1. **Consip – Ricerca gare**
   - Procedure sopra e sotto soglia bandite direttamente da Consip.
   - Lettura di titolo, ID Sigef, stato, pubblicazione e collegamento alla scheda.

2. **Open Data Consip – Bandi e Gare del Programma**
   - Convenzioni.
   - Accordi Quadro.
   - Mercato Elettronico.
   - Sistema Dinamico di Acquisizione.

3. **Open Data Consip – Appalti Specifici SDAPA**
   - Appalti specifici pubblicati nell'ambito dei bandi SDAPA.

4. **Open Data Consip – RDO e TD MePA**
   - Richieste di Offerta e Trattative Dirette presenti nel dataset pubblico.
   - Le procedure riservate visibili soltanto dopo autenticazione non possono essere garantite.

## Migliorie

- Scansione parallela.
- Individuazione automatica della risorsa JSON/CSV dell'anno corrente tramite API CKAN.
- Ricerca per parole chiave e CPV.
- Deduplicazione tra Consip, ANAC, TED e portali regionali.
- Evidenza delle gare nuove e delle gare aggiornate.
- Conservazione dello storico.
- Una fonte offline non interrompe il workflow.

## Installazione

1. Estrarre lo ZIP.
2. Sostituire tutti i file del repository GitHub.
3. Verificare che sia presente `.github/workflows/scan.yml`.
4. Aprire `Actions`.
5. Selezionare `Scansione bandi v5 Consip`.
6. Premere `Run workflow`.

## Nota

I dataset Consip vengono aggiornati con la frequenza prevista dal portale Open Data. Per le opportunità più recenti il radar controlla anche la pagina pubblica “Ricerca gare”.
