from __future__ import annotations

import csv
import io
import hashlib
import json
import os
import re
import smtplib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data/gare.json"
CSV_FILE = ROOT / "data/gare.csv"
SETTINGS = CONFIG["settings"]
KEYWORDS = [x.lower() for x in CONFIG["keywords"]]
NEGATIVE = [x.lower() for x in CONFIG.get("negative_keywords", [])]
CPV_CODES = CONFIG["cpv"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarAppalti/4.0; GitHub Actions)",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
}
REQUEST_TIMEOUT = (
    SETTINGS.get("connection_timeout_seconds", 5),
    SETTINGS.get("read_timeout_seconds", 10),
)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def make_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()[:24]


def relevant(text: str) -> bool:
    low = text.lower()
    positive = any(word in low for word in KEYWORDS) or any(code in low for code in CPV_CODES)
    negative = any(word in low for word in NEGATIVE)
    return positive and not negative


def classify(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ("multiservizi", "multi servizi", "global service", "facility management", "servizi integrati")):
        return "Multiservizi"
    if any(x in low for x in ("portier", "reception", "custodia", "guardiania non armata", "controllo accessi", "front office", "accoglienza")):
        return "Portierato"
    if any(x in low for x in ("sanific", "disinfe", "disinfest", "derattizz")):
        return "Sanificazione"
    if any(x in low for x in ("pulizia", "pulizie", "igiene ambientale")):
        return "Pulizie"
    if any(x in low for x in ("facchinaggio", "movimentazione")):
        return "Facchinaggio"
    return "Servizi"


def extract_cpv(text: str) -> str:
    for code in CPV_CODES:
        if code in text:
            return code
    match = re.search(r"\b(\d{8})(?:-\d)?\b", text)
    return match.group(1) if match else ""


def extract_cig(text: str) -> str:
    match = re.search(r"\bCIG[\s:.-]*([A-Z0-9]{10})\b", text, re.I)
    return match.group(1).upper() if match else ""


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        return dateparser.parse(value, dayfirst=True).strftime("%d/%m/%Y")
    except Exception:
        return ""


def date_near(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = label + r"[^\d]{0,55}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})"
        match = re.search(pattern, text, re.I)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
    return ""


def extract_amount(text: str) -> str:
    match = re.search(r"(?:€|euro)\s*([\d\.\,]+)", text, re.I)
    return match.group(1) if match else ""


def is_expired(date_value: str) -> bool:
    if not date_value:
        return False
    try:
        return dateparser.parse(date_value, dayfirst=True).date() < datetime.now().date()
    except Exception:
        return False


def priority_score(item: dict[str, Any]) -> int:
    regions = SETTINGS.get("priority_regions", [])
    region = item.get("regione", "")
    points = 25
    if region in regions:
        points += max(5, 40 - regions.index(region) * 4)
    if item.get("cpv"):
        points += 15
    if item.get("scadenza"):
        points += 10
    if item.get("importo"):
        points += 5
    if item.get("categoria") in {"Pulizie", "Portierato", "Multiservizi", "Sanificazione"}:
        points += 10
    return min(100, points)


def tender_from_text(
    *,
    title: str,
    text: str,
    source: dict[str, Any],
    url: str,
    publication: str = "",
    deadline: str = "",
    entity: str = "",
) -> dict[str, Any]:
    item = {
        "id": make_id(extract_cig(text) or url or source["name"] + title),
        "titolo": clean(title)[:600],
        "ente": clean(entity) or source["name"],
        "categoria": classify(text),
        "cpv": extract_cpv(text),
        "cig": extract_cig(text),
        "regione": source.get("region", ""),
        "provincia": "",
        "pubblicazione": publication or date_near(text, ("pubblicazione", "pubblicato", "data pubblicazione")),
        "scadenza": deadline or date_near(text, ("scadenza", "termine", "entro", "presentazione offerte")),
        "importo": extract_amount(text),
        "fonte": source["name"],
        "url": url,
        "rilevato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    item["punteggio"] = priority_score(item)
    return item


def get_html(session: requests.Session, url: str, timeout=None) -> tuple[str, str]:
    response = session.get(url, headers=HEADERS, timeout=timeout or REQUEST_TIMEOUT)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("risposta vuota")
    return response.text, response.url


def page_text(html: str) -> tuple[BeautifulSoup, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup, clean(soup.get_text(" ", strip=True))


def scan_anac(source: dict[str, Any]) -> list[dict[str, Any]]:
    session = requests.Session()
    html, final_url = get_html(session, source["url"])
    soup, _ = page_text(html)
    results = []
    seen = set()

    headings = soup.find_all(["h5", "h6", "article", "li", "div"])
    for block in headings:
        text = clean(block.get_text(" ", strip=True))
        if len(text) < 45 or not relevant(text):
            continue
        link = block.find("a", href=True)
        if not link:
            continue
        url = urljoin(final_url, link["href"])
        if "/bandi/" not in url or url in seen:
            continue
        seen.add(url)

        title_node = block.find(["h5", "h6", "strong"])
        title = clean(title_node.get_text(" ", strip=True) if title_node else link.get_text(" ", strip=True))
        if len(title) < 12:
            title = text[:280]

        entity = ""
        for node in block.find_all(["h5", "h6", "strong"]):
            candidate = clean(node.get_text(" ", strip=True))
            if candidate and candidate != title and len(candidate) < 180:
                entity = candidate
                break

        item = tender_from_text(
            title=title,
            text=text,
            source=source,
            url=url,
            publication=date_near(text, ("pubblicato", "pubblicazione")),
            deadline=date_near(text, ("scadenza",)),
            entity=entity,
        )
        if not SETTINGS.get("exclude_expired", True) or not is_expired(item["scadenza"]):
            results.append(item)

    return deduplicate(results)


def ted_query() -> str:
    # Ricerca italiana per CPV. I codici con * comprendono le sottocategorie.
    cpv_terms = " OR ".join(f'classification-cpv = "{code}"' for code in CPV_CODES[:20])
    return f'place-of-performance = "ITA" AND ({cpv_terms})'


def first_value(obj: Any, keys: tuple[str, ...]) -> str:
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, dict):
                    found = first_value(first, keys)
                    if found:
                        return found
        for value in obj.values():
            found = first_value(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = first_value(value, keys)
            if found:
                return found
    return ""


def scan_ted_api(source: dict[str, Any]) -> list[dict[str, Any]]:
    payload_variants = [
        {
            "query": ted_query(),
            "fields": [
                "publication-number", "notice-title", "buyer-name",
                "publication-date", "deadline-receipt-tender-date",
                "classification-cpv", "place-of-performance"
            ],
            "page": 1,
            "limit": 100,
            "scope": "ALL"
        },
        {
            "query": ted_query(),
            "fields": [
                "publication-number", "notice-title", "buyer-name",
                "publication-date", "deadline-receipt-tender-date",
                "classification-cpv"
            ],
            "page": 1,
            "limit": 100
        }
    ]

    session = requests.Session()
    last_error = None
    data = None
    for payload in payload_variants:
        try:
            response = session.post(
                source["url"],
                json=payload,
                headers={**HEADERS, "Content-Type": "application/json", "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            break
        except Exception as exc:
            last_error = exc

    if data is None:
        raise RuntimeError(f"TED API non disponibile: {last_error}")

    notices = []
    if isinstance(data, dict):
        for key in ("notices", "results", "items", "content"):
            if isinstance(data.get(key), list):
                notices = data[key]
                break
    elif isinstance(data, list):
        notices = data

    results = []
    for notice in notices:
        title = first_value(notice, ("notice-title", "title", "noticeTitle"))
        entity = first_value(notice, ("buyer-name", "buyerName", "organisation-name"))
        publication_number = first_value(notice, ("publication-number", "publicationNumber", "notice-id"))
        publication = parse_date(first_value(notice, ("publication-date", "publicationDate")))
        deadline = parse_date(first_value(notice, ("deadline-receipt-tender-date", "deadline", "submission-deadline")))
        cpv_value = first_value(notice, ("classification-cpv", "cpv", "main-cpv"))
        text = clean(json.dumps(notice, ensure_ascii=False))

        if not title or not relevant(text + " " + title + " " + cpv_value):
            continue

        url = f"https://ted.europa.eu/it/notice/-/detail/{publication_number}" if publication_number else "https://ted.europa.eu/"
        item = tender_from_text(
            title=title,
            text=text + " " + cpv_value,
            source=source,
            url=url,
            publication=publication,
            deadline=deadline,
            entity=entity,
        )
        if cpv_value and not item["cpv"]:
            item["cpv"] = re.sub(r"\D", "", cpv_value)[:8]
        item["punteggio"] = priority_score(item)

        if not SETTINGS.get("exclude_expired", True) or not is_expired(item["scadenza"]):
            results.append(item)

    return deduplicate(results)


def detail_text(session: requests.Session, url: str) -> str:
    try:
        html, _ = get_html(
            session,
            url,
            timeout=(
                SETTINGS.get("connection_timeout_seconds", 5),
                SETTINGS.get("detail_timeout_seconds", 6),
            ),
        )
        _, text = page_text(html)
        return text[:25000]
    except Exception:
        return ""


def scan_generic(source: dict[str, Any]) -> list[dict[str, Any]]:
    session = requests.Session()
    urls = source.get("urls") or [source.get("url")]
    last_error = None

    for source_url in [u for u in urls if u]:
        try:
            html, final_url = get_html(session, source_url)
            soup, _ = page_text(html)
            candidates = []
            seen_links = set()

            for link in soup.find_all("a", href=True):
                title = clean(link.get_text(" ", strip=True))
                if len(title) < 12:
                    continue
                url = urljoin(final_url, link["href"])
                if url.startswith(("javascript:", "mailto:", "tel:")) or url in seen_links:
                    continue
                seen_links.add(url)
                context = clean((link.parent or link).get_text(" ", strip=True))
                combined = clean(title + " " + context)

                if relevant(combined):
                    candidates.append((title, combined, url, True))
                elif any(word in combined.lower() for word in ("gara", "bando", "procedura", "affidamento", "avviso")):
                    candidates.append((title, combined, url, False))

                if len(candidates) >= SETTINGS.get("max_links_per_source", 70):
                    break

            results = []
            details_used = 0
            for title, combined, url, already_relevant in candidates:
                text = combined
                if not already_relevant and details_used < SETTINGS.get("max_detail_pages_per_source", 12):
                    details_used += 1
                    text = clean(text + " " + detail_text(session, url))
                if not relevant(text):
                    continue

                item = tender_from_text(title=title, text=text, source=source, url=url)
                if not SETTINGS.get("exclude_expired", True) or not is_expired(item["scadenza"]):
                    results.append(item)

            return deduplicate(results)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(str(last_error or "nessun URL disponibile"))


def normalized_record(record: dict[str, Any]) -> dict[str, str]:
    return {
        re.sub(r"[^a-z0-9]+", "_", clean(key).lower()).strip("_"): clean(value)
        for key, value in record.items()
    }


def find_field(record: dict[str, str], *needles: str) -> str:
    for needle in needles:
        needle = needle.lower()
        for key, value in record.items():
            if needle in key and value:
                return value
    return ""


def records_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("records", "result", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = records_from_json(value)
                if nested:
                    return nested
    return []


def scan_consip_ckan(source: dict[str, Any]) -> list[dict[str, Any]]:
    session = requests.Session()
    response = session.get(source["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    package = response.json()
    if not package.get("success"):
        raise RuntimeError("CKAN non ha restituito il dataset")

    resources = package.get("result", {}).get("resources", [])
    current_year = str(datetime.now().year)

    def resource_rank(resource: dict[str, Any]) -> tuple[int, int]:
        fmt = clean(resource.get("format")).upper()
        name = clean(resource.get("name") or resource.get("url"))
        format_rank = 3 if fmt == "JSON" else 2 if fmt == "CSV" else 0
        year_rank = 2 if current_year in name else 1
        return year_rank, format_rank

    usable = [
        r for r in resources
        if clean(r.get("format")).upper() in {"JSON", "CSV"}
        and r.get("url")
    ]
    if not usable:
        raise RuntimeError("nessuna risorsa JSON/CSV disponibile")

    usable.sort(key=resource_rank, reverse=True)
    resource = usable[0]
    data_response = session.get(resource["url"], headers=HEADERS, timeout=(7, 25))
    data_response.raise_for_status()

    if clean(resource.get("format")).upper() == "JSON":
        records = records_from_json(data_response.json())
    else:
        text = data_response.content.decode("utf-8-sig", errors="replace")
        sample = text[:5000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        except Exception:
            dialect = csv.excel
            dialect.delimiter = ";"
        records = list(csv.DictReader(io.StringIO(text), dialect=dialect))

    results = []
    for raw in records:
        rec = normalized_record(raw)
        title = find_field(
            rec, "oggetto", "descrizione_iniziativa", "nome_iniziativa",
            "denominazione_iniziativa", "titolo", "descrizione"
        )
        entity = find_field(
            rec, "amministrazione", "stazione_appaltante", "ente",
            "ragione_sociale", "soggetto_aggiudicatore"
        )
        cpv = find_field(rec, "cpv")
        category = find_field(rec, "categoria", "merceologica")
        combined = clean(" ".join([title, entity, cpv, category] + list(rec.values())))

        if not title or not relevant(combined):
            continue

        deadline = parse_date(find_field(
            rec, "data_scadenza", "scadenza", "termine_presentazione",
            "data_fine_presentazione"
        ))
        publication = parse_date(find_field(
            rec, "data_pubblicazione", "pubblicazione", "data_bando"
        ))
        cig = find_field(rec, "cig")
        sigef = find_field(rec, "sigef", "id_iniziativa", "numero_iniziativa")
        url = find_field(rec, "url", "link")
        if not url:
            url = "https://www.acquistinretepa.it/opencms/opencms/vetrina_bandi.html"
        if sigef and not url.startswith("http"):
            url = "https://www.consip.it/imprese/bandi"

        item = tender_from_text(
            title=title,
            text=combined,
            source=source,
            url=url,
            publication=publication,
            deadline=deadline,
            entity=entity or "Consip / Amministrazione pubblica",
        )
        if cig:
            item["cig"] = cig
            item["id"] = make_id(cig)
        elif sigef:
            item["id"] = make_id(source["name"] + sigef)
        if cpv and not item["cpv"]:
            item["cpv"] = re.sub(r"\D", "", cpv)[:8]
        item["strumento"] = find_field(rec, "strumento", "tipologia_procedura", "tipo_iniziativa")
        item["stato"] = find_field(rec, "stato", "fase")
        item["punteggio"] = priority_score(item)

        if not SETTINGS.get("exclude_expired", True) or not is_expired(item["scadenza"]):
            results.append(item)

    return deduplicate(results)


def scan_consip_gare(source: dict[str, Any]) -> list[dict[str, Any]]:
    session = requests.Session()
    html, final_url = get_html(session, source["url"], timeout=(7, 18))
    soup, page = page_text(html)
    results = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = urljoin(final_url, link["href"])
        if "/bandi/" not in href or href in seen:
            continue
        title = clean(link.get_text(" ", strip=True))
        if len(title) < 20:
            continue
        parent = link
        for _ in range(4):
            if parent.parent:
                parent = parent.parent
        context = clean(parent.get_text(" ", strip=True))
        combined = clean(title + " " + context)
        if not relevant(combined):
            continue
        seen.add(href)

        sigef_match = re.search(r"\bID\s*Sigef\s*(\d+)", combined, re.I)
        item = tender_from_text(
            title=title,
            text=combined,
            source=source,
            url=href,
            publication=date_near(combined, ("pubblicazione", "pubblicato")),
            deadline=date_near(combined, ("ricezione offerte", "scadenza", "termine")),
            entity="Consip S.p.A.",
        )
        if sigef_match:
            item["id_sigef"] = sigef_match.group(1)
            item["id"] = make_id("CONSIP-SIGEF-" + sigef_match.group(1))
        item["punteggio"] = priority_score(item) + 5
        results.append(item)

    return deduplicate(results)

def scan_source(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    started = time.monotonic()
    adapter = source.get("adapter", "generic")

    if adapter == "anac":
        items = scan_anac(source)
    elif adapter == "ted_api":
        items = scan_ted_api(source)
    elif adapter == "consip_ckan":
        items = scan_consip_ckan(source)
    elif adapter == "consip_gare":
        items = scan_consip_gare(source)
    else:
        items = scan_generic(source)

    elapsed = round(time.monotonic() - started, 2)
    return items, f"{elapsed}s"


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = {}
    for item in items:
        key = item.get("cig") or item.get("url") or item["id"]
        output[key] = item
    return list(output.values())


def keep_recent_old(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = datetime.now() - timedelta(days=SETTINGS.get("retention_days", 180))
    output = []
    for item in items:
        value = item.get("rilevato_il", "")
        try:
            detected = dateparser.parse(value, dayfirst=True)
            if detected >= cutoff:
                output.append(item)
        except Exception:
            output.append(item)
    return output


def notify(items: list[dict[str, Any]]) -> None:
    if not items:
        return

    text = f"Radar Appalti: {len(items)} nuove opportunità\n\n"
    text += "\n\n".join(
        f"• {item['titolo']}\n{item.get('ente', '')} — "
        f"{item.get('scadenza') or 'scadenza da verificare'}\n{item.get('url', '')}"
        for item in items[:12]
    )

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text[:4000],
                    "disable_web_page_preview": True,
                },
                timeout=10,
            ).raise_for_status()
        except Exception as exc:
            print(f"Notifica Telegram non inviata: {exc}", file=sys.stderr)

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    recipient = os.getenv("ALERT_EMAIL", "")
    if smtp_host and smtp_user and smtp_password and recipient:
        try:
            message = EmailMessage()
            message["Subject"] = f"Radar Appalti: {len(items)} nuove gare"
            message["From"] = smtp_user
            message["To"] = recipient
            message.set_content(text)
            with smtplib.SMTP_SSL(smtp_host, int(os.getenv("SMTP_PORT", "465")), timeout=12) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(message)
        except Exception as exc:
            print(f"Notifica email non inviata: {exc}", file=sys.stderr)


def write_csv(items: list[dict[str, Any]]) -> None:
    fields = [
        "titolo", "ente", "categoria", "cpv", "cig", "regione",
        "pubblicazione", "scadenza", "importo", "fonte", "url",
        "punteggio", "rilevato_il"
    ]
    with CSV_FILE.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        writer.writerows(items)


def main() -> None:
    old_payload = {"gare": []}
    if DATA_FILE.exists():
        try:
            old_payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    old_items = keep_recent_old(old_payload.get("gare", []))
    old_ids = {item["id"] for item in old_items if item.get("id")}
    old_by_id = {item["id"]: item for item in old_items if item.get("id")}
    merged = dict(old_by_id)
    statuses = []
    new_items = []
    updated_items = []

    sources = [source for source in CONFIG["sources"] if source.get("active", True)]
    workers = min(SETTINGS.get("max_workers", 8), max(1, len(sources)))

    print(f"Avvio scansione parallela di {len(sources)} fonti con {workers} worker.")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(scan_source, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                items, elapsed = future.result()
                for item in items:
                    previous = old_by_id.get(item["id"])
                    if previous is None:
                        item["novita"] = "Nuova"
                        new_items.append(item)
                    else:
                        comparable = ("titolo", "ente", "scadenza", "importo", "stato", "url")
                        changed = any(clean(previous.get(k)) != clean(item.get(k)) for k in comparable)
                        if changed:
                            item["novita"] = "Aggiornata"
                            updated_items.append(item)
                        else:
                            item["novita"] = previous.get("novita", "")
                    merged[item["id"]] = item
                statuses.append({
                    "fonte": source["name"],
                    "ok": True,
                    "trovate": len(items),
                    "tempo": elapsed,
                    "errore": "",
                })
                print(f"OK {source['name']}: {len(items)} risultati in {elapsed}")
            except Exception as exc:
                statuses.append({
                    "fonte": source["name"],
                    "ok": False,
                    "trovate": 0,
                    "tempo": "",
                    "errore": clean(exc)[:300],
                })
                print(f"ERRORE {source['name']}: {exc}", file=sys.stderr)

    items = sorted(
        merged.values(),
        key=lambda item: (
            -int(item.get("punteggio", 0)),
            item.get("scadenza") or "99/99/9999",
            item.get("titolo", ""),
        ),
    )

    payload = {
        "version": CONFIG.get("version", "4.0"),
        "updated_at": datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        "count": len(items),
        "new_count": len(new_items),
        "updated_count": len(updated_items),
        "sources_ok": sum(1 for status in statuses if status["ok"]),
        "sources_error": sum(1 for status in statuses if not status["ok"]),
        "sources_status": sorted(statuses, key=lambda status: status["fonte"]),
        "gare": items,
    }

    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(items)
    notify(new_items)

    print(
        f"Scansione terminata: {len(items)} gare archiviate, "
        f"{len(new_items)} nuove, {len(updated_items)} aggiornate, "
        f"{payload['sources_ok']} fonti OK, "
        f"{payload['sources_error']} fonti con errore."
    )


if __name__ == "__main__":
    main()
