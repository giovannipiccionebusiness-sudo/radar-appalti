# Radar Appalti — versione GitHub Pages

Questa versione funziona senza Google Apps Script.

## Cosa usa

- **GitHub Pages** per pubblicare la web app.
- **GitHub Actions** per controllare automaticamente le fonti.
- **data/gare.json** come archivio delle opportunità.
- **localStorage** del telefono per preferiti e stato delle gare.

## Installazione da smartphone

1. Crea un nuovo repository GitHub, per esempio `radar-appalti`.
2. Estrai questo ZIP.
3. Carica nel repository tutti i file e le cartelle, compresa `.github`.
4. Nel repository apri **Settings → Pages**.
5. In **Build and deployment**, scegli:
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Cartella: `/ (root)`
6. Salva.
7. Apri **Actions**, seleziona `Scansione bandi` e premi **Run workflow**.
8. Dopo il primo aggiornamento, GitHub Pages mostrerà i risultati.

L'indirizzo sarà simile a:

`https://TUO-UTENTE.github.io/radar-appalti/`

## Aggiornamento automatico

Il file `.github/workflows/scan.yml` avvia la scansione ogni giorno alle 05:15 UTC, cioè generalmente alle 07:15 in Italia durante l'ora legale.

Puoi avviarla anche manualmente:

**Actions → Scansione bandi → Run workflow**

## Aggiungere una fonte

Apri `config.json` e aggiungi un elemento dentro `sources`:

```json
{
  "active": true,
  "name": "Nome ente",
  "type": "html",
  "url": "https://www.esempio.it/bandi",
  "region": "Puglia"
}
```

Dopo il salvataggio esegui nuovamente il workflow.

## Limite importante

Alcuni portali caricano i dati con JavaScript, CAPTCHA oppure API non pubbliche. L'estrattore generico potrebbe non leggerli correttamente. In quel caso serve un adattatore specifico nel file `scripts/scan.py`.

## File principali

- `index.html`: interfaccia.
- `assets/app.js`: filtri, preferiti e stati.
- `scripts/scan.py`: motore di scansione.
- `config.json`: parole chiave, CPV e fonti.
- `.github/workflows/scan.yml`: esecuzione automatica.
- `data/gare.json`: archivio.
