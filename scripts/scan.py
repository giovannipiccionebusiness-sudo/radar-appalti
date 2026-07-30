from __future__ import annotations
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data/gare.json"

KEYWORDS = [k.lower() for k in CONFIG["keywords"]]
CPV = CONFIG["cpv"]
TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 RadarAppaltiGitHub/1.0"}

def make_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()[:24]

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def relevant(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in KEYWORDS) or any(c in low for c in CPV)

def category(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ["multiservizi", "global service", "facility management", "servizi integrati"]): return "Multiservizi"
    if any(x in low for x in ["portierato", "portineria", "reception", "custodia", "guardiania"]): return "Portierato"
    if any(x in low for x in ["sanificazione", "disinfezione"]): return "Sanificazione"
    if any(x in low for x in ["pulizia", "pulizie", "igiene ambientale"]): return "Pulizie"
    if "facchinaggio" in low: return "Facchinaggio"
    return "Servizi"

def first_cpv(text: str) -> str:
    for code in CPV:
        if code in text:
            return code
    m = re.search(r"\b(?:CPV\s*)?(\d{8})(?:-\d)?\b", text, re.I)
    return m.group(1) if m else ""

def extract_date(text: str, labels: list[str]) -> str:
    for label in labels:
        m = re.search(label + r"[^\d]{0,40}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})", text, re.I)
        if m:
            try:
                d = dateparser.parse(m.group(1), dayfirst=True)
                return d.strftime("%d/%m/%Y")
            except Exception:
                pass
    return ""

def extract_amount(text: str) -> str:
    m = re.search(r"(?:€|euro)\s*([\d\.\,]+)", text, re.I)
    return m.group(1) if m else ""

def fetch_html_source(source: dict) -> list[dict]:
    response = requests.get(source["url"], timeout=TIMEOUT, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out, seen = [], set()
    links = soup.find_all("a", href=True)
    for link in links:
        title = clean(link.get_text(" ", strip=True))
        if len(title) < 18:
            continue
        parent_text = clean((link.parent or link).get_text(" ", strip=True))
        text = clean(title + " " + parent_text)
        if not relevant(text):
            continue
        url = urljoin(source["url"], link["href"])
        key = (title.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": make_id(url or source["name"] + title),
            "titolo": title[:500],
            "ente": source["name"],
            "categoria": category(text),
            "cpv": first_cpv(text),
            "regione": source.get("region", ""),
            "provincia": "",
            "pubblicazione": extract_date(text, ["pubblicazione", "pubblicato", "data"]),
            "scadenza": extract_date(text, ["scadenza", "termine", "entro"]),
            "importo": extract_amount(text),
            "fonte": source["name"],
            "url": url,
            "rilevato_il": datetime.now().strftime("%d/%m/%Y %H:%M")
        })
    return out

def main() -> None:
    old = {"gare": []}
    if DATA_FILE.exists():
        old = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    by_id = {x["id"]: x for x in old.get("gare", [])}

    errors = []
    for source in CONFIG["sources"]:
        if not source.get("active", True):
            continue
        try:
            for tender in fetch_html_source(source):
                by_id.setdefault(tender["id"], tender)
            print(f"OK: {source['name']}")
        except Exception as exc:
            errors.append(f"{source['name']}: {exc}")
            print(f"ERRORE: {source['name']}: {exc}", file=sys.stderr)

    gare = sorted(by_id.values(), key=lambda x: (x.get("scadenza") or "99/99/9999", x.get("titolo","")))
    payload = {
        "updated_at": datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        "count": len(gare),
        "errors": errors,
        "gare": gare
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
