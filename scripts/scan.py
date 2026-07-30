from __future__ import annotations
import csv, hashlib, json, os, re, smtplib, sys, time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
DATA_FILE=ROOT/"data/gare.json"
CSV_FILE=ROOT/"data/gare.csv"
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; RadarAppalti/2.0; +GitHub Actions)"}
KEYWORDS=[x.lower() for x in CONFIG["keywords"]]
NEGATIVE=[x.lower() for x in CONFIG.get("negative_keywords",[])]
CPV=CONFIG["cpv"]
SETTINGS=CONFIG.get("settings",{})

def norm(s): return re.sub(r"\s+"," ",s or "").strip()
def ident(s): return hashlib.sha256(s.encode("utf-8","ignore")).hexdigest()[:24]
def relevant(text):
    s=text.lower()
    positive=any(k in s for k in KEYWORDS) or any(c in s for c in CPV)
    negative=any(k in s for k in NEGATIVE)
    return positive and not negative
def classify(s):
    s=s.lower()
    if any(x in s for x in ["multiservizi","multi servizi","global service","facility management","servizi integrati"]): return "Multiservizi"
    if any(x in s for x in ["portier","reception","custodia","guardiania non armata","controllo accessi","front office","accoglienza"]): return "Portierato"
    if any(x in s for x in ["sanific","disinfe","disinfest","derattizz","pest control"]): return "Sanificazione"
    if any(x in s for x in ["pulizia","pulizie","igiene ambientale"]): return "Pulizie"
    if any(x in s for x in ["facchinaggio","movimentazione"]): return "Facchinaggio"
    return "Servizi"
def cpv(text):
    for c in CPV:
        if c in text: return c
    m=re.search(r"\b(\d{8})(?:-\d)?\b",text)
    return m.group(1) if m else ""
def date_near(text, labels):
    for lab in labels:
        m=re.search(lab+r"[^\d]{0,50}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",text,re.I)
        if m:
            try:return dateparser.parse(m.group(1),dayfirst=True).strftime("%d/%m/%Y")
            except:pass
    return ""
def amount(text):
    m=re.search(r"(?:€|euro)\s*([\d\.\,]+)",text,re.I)
    return m.group(1) if m else ""
def cig(text):
    m=re.search(r"\b(?:CIG\s*)?([A-Z0-9]{10})\b",text,re.I)
    return m.group(1).upper() if m else ""
def expired(s):
    if not s:return False
    try:return dateparser.parse(s,dayfirst=True).date()<datetime.now().date()
    except:return False
def region_score(region):
    priorities=SETTINGS.get("regions_priority",[])
    return max(0,100-(priorities.index(region)*5)) if region in priorities else 20
def score(t):
    value=region_score(t.get("regione",""))
    if t.get("cpv"): value+=20
    if t.get("scadenza"): value+=10
    if t.get("importo"): value+=5
    if t.get("categoria") in ("Pulizie","Portierato","Multiservizi","Sanificazione"): value+=15
    return min(100,value)

def detail_text(session,url):
    try:
        r=session.get(url,headers=HEADERS,timeout=25)
        if r.status_code>=400:return ""
        soup=BeautifulSoup(r.text,"html.parser")
        for tag in soup(["script","style","noscript"]):tag.decompose()
        return norm(soup.get_text(" ",strip=True))[:30000]
    except:return ""

def scan_source(source):
    session=requests.Session()
    r=session.get(source["url"],headers=HEADERS,timeout=30)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    for tag in soup(["script","style","noscript"]):tag.decompose()
    results=[]; seen=set(); limit=int(SETTINGS.get("detail_pages_limit",80))
    candidates=[]
    for a in soup.find_all("a",href=True):
        title=norm(a.get_text(" ",strip=True))
        if len(title)<12:continue
        context=norm((a.parent or a).get_text(" ",strip=True))
        url=urljoin(source["url"],a["href"])
        if url.startswith("javascript:") or url.startswith("mailto:"):continue
        prelim=norm(title+" "+context)
        if relevant(prelim) or any(w in prelim.lower() for w in ["bando","gara","procedura","avviso","affidamento"]):
            candidates.append((title,context,url))
    for title,context,url in candidates[:limit]:
        if url in seen:continue
        seen.add(url)
        full=norm(title+" "+context)
        if not relevant(full):
            full=norm(full+" "+detail_text(session,url))
            time.sleep(float(SETTINGS.get("request_delay_seconds",0)))
        if not relevant(full):continue
        tender={
          "id":ident(cig(full) or url or source["name"]+title),
          "titolo":title[:500],"ente":source["name"],"categoria":classify(full),
          "cpv":cpv(full),"cig":cig(full),"regione":source.get("region",""),"provincia":"",
          "pubblicazione":date_near(full,["pubblicazione","pubblicato","data pubblicazione"]),
          "scadenza":date_near(full,["scadenza","termine","entro","presentazione offerte"]),
          "importo":amount(full),"fonte":source["name"],"url":url,
          "rilevato_il":datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        tender["punteggio"]=score(tender)
        if SETTINGS.get("exclude_expired",True) and expired(tender["scadenza"]):continue
        results.append(tender)
    return results

def notify(new_items):
    if not new_items:return
    telegram_token=os.getenv("TELEGRAM_BOT_TOKEN","")
    telegram_chat=os.getenv("TELEGRAM_CHAT_ID","")
    text="Radar Appalti: %d nuove opportunità\n\n"%len(new_items)
    text+="\n\n".join(f"• {x['titolo']}\n{x.get('ente','')} — {x.get('scadenza') or 'scadenza da verificare'}\n{x['url']}" for x in new_items[:15])
    if telegram_token and telegram_chat:
        try:requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage",json={"chat_id":telegram_chat,"text":text[:4000],"disable_web_page_preview":True},timeout=20)
        except Exception as e:print("Telegram:",e,file=sys.stderr)
    host=os.getenv("SMTP_HOST",""); user=os.getenv("SMTP_USER",""); password=os.getenv("SMTP_PASSWORD",""); recipient=os.getenv("ALERT_EMAIL","")
    if host and user and password and recipient:
        try:
            msg=EmailMessage();msg["Subject"]=f"Radar Appalti: {len(new_items)} nuove gare";msg["From"]=user;msg["To"]=recipient;msg.set_content(text)
            with smtplib.SMTP_SSL(host,int(os.getenv("SMTP_PORT","465"))) as s:s.login(user,password);s.send_message(msg)
        except Exception as e:print("Email:",e,file=sys.stderr)

def write_csv(gare):
    fields=["titolo","ente","categoria","cpv","cig","regione","pubblicazione","scadenza","importo","fonte","url","punteggio","rilevato_il"]
    with CSV_FILE.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",delimiter=";");w.writeheader();w.writerows(gare)

def main():
    old={"gare":[]}
    if DATA_FILE.exists():old=json.loads(DATA_FILE.read_text(encoding="utf-8"))
    old_ids={x["id"] for x in old.get("gare",[])}
    merged={x["id"]:x for x in old.get("gare",[])}
    statuses=[]; fresh=[]
    for source in sorted(CONFIG["sources"],key=lambda x:x.get("priority",9)):
        if not source.get("active",True):continue
        try:
            items=scan_source(source)
            for x in items:
                if x["id"] not in merged:fresh.append(x)
                merged[x["id"]]=x
            statuses.append({"fonte":source["name"],"ok":True,"trovate":len(items),"errore":""})
            print("OK",source["name"],len(items))
        except Exception as e:
            statuses.append({"fonte":source["name"],"ok":False,"trovate":0,"errore":str(e)[:250]})
            print("ERRORE",source["name"],e,file=sys.stderr)
    gare=sorted(merged.values(),key=lambda x:(-int(x.get("punteggio",0)),x.get("scadenza") or "99/99/9999"))
    payload={"updated_at":datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),"count":len(gare),"new_count":len(fresh),"sources_status":statuses,"gare":gare}
    DATA_FILE.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv(gare);notify(fresh)

if __name__=="__main__":main()
