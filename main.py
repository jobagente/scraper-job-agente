import os
import sys
import json
import time
import re
import requests
import urllib3
import gspread
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse, urljoin
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

creds_json = os.environ.get('GCP_CREDENTIALS')
gemini_keys_raw = os.environ.get('GEMINI_API_KEY', '')
hubspot_token = os.environ.get('HUBSPOT_ACCESS_TOKEN')
serper_api_key = os.environ.get('SERPER_API_KEY')

if not creds_json:
    raise ValueError("ERRORE: Variabile GCP_CREDENTIALS mancante.")

creds_dict = json.loads(creds_json)
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

LISTA_CHIAVI = [k.strip() for k in re.split(r'[,;\s\n]+', gemini_keys_raw) if k.strip()]
for idx_k in range(2, 15):
    extra_k = (os.environ.get(f'GEMINI_API_KEY_{idx_k}') or '').strip()
    if extra_k and extra_k not in LISTA_CHIAVI:
        LISTA_CHIAVI.append(extra_k)

CLIENTS_POOL = []
for idx, k in enumerate(LISTA_CHIAVI, start=1):
    try:
        c = genai.Client(api_key=k, http_options=types.HttpOptions(timeout=60000))
        CLIENTS_POOL.append({
            "id": f"Chiave #{idx} (...{k[-4:]})",
            "client": c,
            "modelli": ['gemini-3.8-flash']
        })
    except Exception as e_cl:
        print(f"Errore inizializzazione Chiave #{idx}: {e_cl}")

if CLIENTS_POOL:
    try:
        modelli_extra = []
        escl_mod = (
            'vision', 'embedding', 'imagen', 'veo', 'audio',
            'tts', 'aqa', 'bisect', '2.0', '1.5', '2.5', 'pro'
        )
        for m in CLIENTS_POOL[0]["client"].models.list():
            nome = m.name.replace('models/', '')
            if 'gemini-' in nome and not any(x in nome for x in escl_mod):
                if nome not in modelli_extra and nome != 'gemini-3.8-flash':
                    modelli_extra.append(nome)
        for item in CLIENTS_POOL:
            item["modelli"].extend(modelli_extra)
    except Exception:
        pass

print(f"Chiavi Gemini caricate nel pool: {len(CLIENTS_POOL)}")
for item in CLIENTS_POOL:
    print(f"   - {item['id']} -> Modelli: {item['modelli']}")

HEADERS_BROWSER = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'
}

AGGREGATORI_DA_BLOCCARE = (
    'manstar', 'kompass', 'europages', 'informazione-aziende', 'ufficiocamerale',
    'fatturatoitalia', 'signalhire', 'rocketreach', 'zoominfo', 'dnb.com',
    'crunchbase', 'atoka.io', 'empresite', 'gowork.it', 'casagenti.it',
    'xing.com', 'academia.edu', '.edu.it', '.gov.it', 'lavoraconnoi.com',
    'gazzettadellavoro.com', 'globelife.com', '360forma.com', 'jimdoweb.com',
    'webnode.it', 'webnode.page', 'wixsite.com', 'altervista.org',
    'tutto626.it', 'claude.com', 'job4italy.com', 'trendsrl.net',
    'profili.it', 'gesacom.it', 'made-in-china.com', 'alibaba.com',
    'agriaffaires.', 'machineryzone.', 'noleggiamoauto.it', 'senato.it',
    'virgilio.it', 'leggo.it', 'mattinopadova.it', 'elledecor.com', 'github.com',
    'infobel.com', 'openedition.org', 'legambiente.it', 'ny.gov', 'unito.it',
    'agent321.', 'freshplaza.it', 'ricercaimprese.com', 'partitaiva24.it',
    'italiaatavola.net', 'informazionesenzafiltro.it', 'eventipress.com'
)

PATH_AGGREGATORI_DA_BLOCCARE = (
    '/companies/', '/company/', '/aziende/', '/azienda/', '/directory/', '/profile/'
)

PAROLE_CHIAVE_AGENTE = (
    'agent', 'rappresentant', 'vendit', 'commercial', 'enasarco',
    'plurimandat', 'monomandat', 'procacciat', 'p.iva', 'p. iva',
    'partita iva', 'rete vendita', 'sales', 'mandat', 'provvigion'
)

MAPPA_PROVINCE_REGIONI = {
    'AG': 'SICILIA', 'AL': 'PIEMONTE', 'AN': 'MARCHE', 'AO': "VALLE D'AOSTA",
    'AR': 'TOSCANA', 'AP': 'MARCHE', 'AT': 'PIEMONTE', 'AV': 'CAMPANIA',
    'BA': 'PUGLIA', 'BT': 'PUGLIA', 'BL': 'VENETO', 'BN': 'CAMPANIA',
    'BG': 'LOMBARDIA', 'BI': 'PIEMONTE', 'BO': 'EMILIA-ROMAGNA',
    'BZ': 'TRENTINO-ALTO ADIGE', 'BS': 'LOMBARDIA', 'BR': 'PUGLIA',
    'CA': 'SARDEGNA', 'CL': 'SICILIA', 'CB': 'MOLISE', 'CE': 'CAMPANIA',
    'CT': 'SICILIA', 'CZ': 'CALABRIA', 'CH': 'ABRUZZO', 'CO': 'LOMBARDIA',
    'CS': 'CALABRIA', 'CR': 'LOMBARDIA', 'KR': 'CALABRIA', 'CN': 'PIEMONTE',
    'EN': 'SICILIA', 'FM': 'MARCHE', 'FE': 'EMILIA-ROMAGNA', 'FI': 'TOSCANA',
    'FG': 'PUGLIA', 'FC': 'EMILIA-ROMAGNA', 'FR': 'LAZIO', 'GE': 'LIGURIA',
    'GO': 'FRIULI-VENEZIA GIULIA', 'GR': 'TOSCANA', 'IM': 'LIGURIA',
    'IS': 'MOLISE', 'SP': 'LIGURIA', 'AQ': 'ABRUZZO', 'LT': 'LAZIO',
    'LE': 'PUGLIA', 'LC': 'LOMBARDIA', 'LI': 'TOSCANA', 'LO': 'LOMBARDIA',
    'LU': 'TOSCANA', 'MC': 'MARCHE', 'MN': 'LOMBARDIA', 'MS': 'TOSCANA',
    'MT': 'BASILICATA', 'ME': 'SICILIA', 'MI': 'LOMBARDIA',
    'MO': 'EMILIA-ROMAGNA', 'MB': 'LOMBARDIA', 'NA': 'CAMPANIA',
    'NO': 'PIEMONTE', 'NU': 'SARDEGNA', 'OR': 'SARDEGNA', 'PD': 'VENETO',
    'PA': 'SICILIA', 'PR': 'EMILIA-ROMAGNA', 'PV': 'LOMBARDIA', 'PG': 'UMBRIA',
    'PU': 'MARCHE', 'PE': 'ABRUZZO', 'PC': 'EMILIA-ROMAGNA', 'PI': 'TOSCANA',
    'PT': 'TOSCANA', 'PN': 'FRIULI-VENEZIA GIULIA', 'PZ': 'BASILICATA',
    'PO': 'TOSCANA', 'RG': 'SICILIA', 'RA': 'EMILIA-ROMAGNA', 'RC': 'CALABRIA',
    'RE': 'EMILIA-ROMAGNA', 'RI': 'LAZIO', 'RN': 'EMILIA-ROMAGNA',
    'RM': 'LAZIO', 'RO': 'VENETO', 'SA': 'CAMPANIA', 'SS': 'SARDEGNA',
    'SV': 'LIGURIA', 'SI': 'TOSCANA', 'SR': 'SICILIA', 'SO': 'LOMBARDIA',
    'SU': 'SARDEGNA', 'TA': 'PUGLIA', 'TE': 'ABRUZZO', 'TR': 'UMBRIA',
    'TO': 'PIEMONTE', 'TP': 'SICILIA', 'TN': 'TRENTINO-ALTO ADIGE',
    'TV': 'VENETO', 'TS': 'FRIULI-VENEZIA GIULIA', 'UD': 'FRIULI-VENEZIA GIULIA',
    'VA': 'LOMBARDIA', 'VE': 'VENETO', 'VB': 'PIEMONTE', 'VC': 'PIEMONTE',
    'VR': 'VENETO', 'VV': 'CALABRIA', 'VI': 'VENETO', 'VT': 'LAZIO'
}

INDICE_CHIAVE_CORRENTE = 0

def ha_capacita_gemini():
    return any(len(item["modelli"]) > 0 for item in CLIENTS_POOL)

def scarica_pagina_sicura(url_sito, timeout_sec=10):
    with requests.get(
        url_sito, headers=HEADERS_BROWSER, timeout=(6, timeout_sec), verify=False, stream=True
    ) as r:
        r.raise_for_status()
        ctype = (r.headers.get('Content-Type') or '').lower()
        if any(b in ctype for b in ('application/pdf', 'image/', 'octet-stream', 'audio/', 'video/')):
            raise ValueError(f"Contenuto non HTML ({ctype})")
        chunks, bytes_letti, inizio = [], 0, time.time()
        for chunk in r.iter_content(chunk_size=16384, decode_unicode=False):
            if chunk:
                chunks.append(chunk)
                bytes_letti += len(chunk)
            if bytes_letti > 350000 or (time.time() - inizio) > timeout_sec:
                break
        encoding = r.encoding or 'utf-8'
        return b"".join(chunks).decode(encoding, errors='replace').replace('\x00', ' ')

def is_partita_iva_italiana(cifre):
    if len(cifre) != 11 or not cifre.isdigit():
        return False
    prov = int(cifre[7:10])
    if not ((1 <= prov <= 121) or prov in (888, 999)):
        return False
    s_disp = sum(int(cifre[i]) for i in range(0, 10, 2))
    s_pari = sum(
        (int(cifre[i]) * 2 - 9 if int(cifre[i]) * 2 > 9 else int(cifre[i]) * 2)
        for i in range(1, 10, 2)
    )
    return ((10 - ((s_disp + s_pari) % 10)) % 10) == int(cifre[10])

def normalizza_telefono_outbound(raw_tel):
    if not raw_tel or raw_tel == "--":
        return "--"
    t = re.sub(
        r'(?i)(tel\.?|telefono|phone|centralino|mob\.?|cell\.?|whatsapp)[:\s]*',
        '', str(raw_tel).strip()
    )
    solo_cifre = re.sub(r'\D', '', t.split('/')[0].split('|')[0])
    if solo_cifre.startswith('0039'):
        solo_cifre = solo_cifre[4:]
    elif solo_cifre.startswith('39') and len(solo_cifre) >= 11:
        solo_cifre = solo_cifre[2:]
    if len(solo_cifre) < 8 or len(solo_cifre) > 11:
        return "--"
    if solo_cifre.startswith('3') and len(solo_cifre) != 10:
        return "--"
    if solo_cifre.startswith('800') and len(solo_cifre) > 9:
        return "--"
    if len(solo_cifre) == 11 and (not solo_cifre.startswith('0') or is_partita_iva_italiana(solo_cifre)):
        return "--"
    if not (solo_cifre.startswith('0') or solo_cifre.startswith('3') or solo_cifre.startswith('800')):
        return "--"
    return f"+39 {solo_cifre}"

def pulisci_testo_da_piva_e_fax(testo):
    return re.sub(
        r'(?i)(?:fax|p\.?\s*iva|partita\s*iva|c\.?\s*f\.?|cod(?:ice)?\s*fisc(?:ale)?|r\.?e\.?a\.?)[:\s.]*[\+\d\s\-\.\(\)/]{8,18}',
        ' ', testo
    )

def estrai_telefoni_da_html(html_text, soup=None):
    if not html_text:
        return "--"
    if soup is None:
        soup = BeautifulSoup(html_text, 'html.parser')
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        if href.lower().startswith('tel:'):
            cand = normalizza_telefono_outbound(href[4:])
            if cand != "--":
                return cand
    testo_pulito = pulisci_testo_da_piva_e_fax(soup.get_text(separator=' ', strip=True))
    pattern_tel = r'(?:\+39|0039)?[\s\.\-]?(?:0\d{1,3}|3\d{2})[\s\.\-\/]?[\d\s\.\-]{5,10}'
    for match in re.findall(pattern_tel, testo_pulito):
        cand = normalizza_telefono_outbound(match)
        if cand != "--":
            return cand
    return "--"

def cerca_telefono_in_pagina_contatti(url_base, soup_iniziale):
    try:
        parsed = urlparse(url_base)
        base_root = f"{parsed.scheme}://{parsed.netloc}"
        link_contatti = None
        if soup_iniziale:
            for a_tag in soup_iniziale.find_all('a', href=True):
                h_low, t_low = a_tag['href'].lower(), a_tag.get_text(strip=True).lower()
                if 'contatt' in h_low or 'contact' in h_low or 'contatt' in t_low:
                    cand_url = urljoin(base_root, a_tag['href'])
                    if estrai_dominio(cand_url) == estrai_dominio(url_base):
                        link_contatti = cand_url
                        break
        link_contatti = link_contatti or f"{base_root}/contatti"
        if link_contatti.rstrip('/') == url_base.rstrip('/'):
            return "--"
        return estrai_telefoni_da_html(scarica_pagina_sicura(link_contatti, timeout_sec=6))
    except Exception:
        return "--"

def estrai_citta_regione_locale(indirizzo):
    if not indirizzo:
        return "--", "--"
    m = re.search(r'\b(\d{5})\s+([A-Za-zÀ-ÿ\'\-\s]+?)\s+([A-Z]{2})\b', indirizzo)
    if m:
        citta, prov = m.group(2).strip().upper(), m.group(3).strip().upper()
        return f"{citta} {prov}", MAPPA_PROVINCE_REGIONI.get(prov, "--")
    return "--", "--"

def parse_risposta_sito(testo_risposta):
    if not testo_risposta:
        return None
    righe_valide = []
    for riga in testo_risposta.splitlines():
        r_clean = riga.replace("*", "").replace("`", "").strip()
        if "|" not in r_clean:
            continue
        parti = [p.strip() for p in r_clean.split("|")]
        p0 = re.sub(r'(?i)^(1\.?\s*)?(esito\s*[:\-]\s*)?', '', parti[0]).strip().upper()
        p1 = parti[1].strip().upper() if len(parti) > 1 else ""
        if p0 == "ESITO" and ("NOME" in p1 or "AZIENDA" in p1 or p1 == ""):
            continue
        parti[0] = p0
        righe_valide.append(parti)
    if not righe_valide:
        return None
    scelta = next(
        (c for c in righe_valide if any(k in c[0] for k in ("AGENTE", "DIPENDENTE", "ESCLUSO"))),
        righe_valide[0]
    )
    raw_esito = scelta[0].upper()
    if "AGENTE" in raw_esito and "NON" not in raw_esito and "ESCLUS" not in raw_esito:
        scelta[0] = "AGENTE"
    elif "DIPENDENT" in raw_esito:
        scelta[0] = "DIPENDENTE"
    else:
        scelta[0] = "ESCLUSO"
    while len(scelta) < 7:
        scelta.append("--")
    return scelta[:7]

def chiama_gemini_con_fallback(prompt, pausa_iniziale=3):
    global INDICE_CHIAVE_CORRENTE
    if not ha_capacita_gemini():
        raise RuntimeError("QUOTA_GIORNALIERA_ESAURITA")
    if pausa_iniziale > 0:
        time.sleep(pausa_iniziale)
    ultimo_errore, risposte_vuote = None, 0
    cfg_veloce = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        temperature=0.1
    )
    tot_chiavi = len(CLIENTS_POOL)

    for giro in range(1, 4):
        for offset in range(tot_chiavi):
            idx = (INDICE_CHIAVE_CORRENTE + offset) % tot_chiavi
            slot = CLIENTS_POOL[idx]
            if not slot["modelli"]:
                continue
            for mod in list(slot["modelli"]):
                try:
                    try:
                        risp = slot["client"].models.generate_content(
                            model=mod, contents=prompt, config=cfg_veloce
                        )
                    except Exception as e_cfg:
                        if 'thinking' in str(e_cfg).lower() or '400' in str(e_cfg):
                            risp = slot["client"].models.generate_content(
                                model=mod, contents=prompt
                            )
                        else:
                            raise e_cfg
                    INDICE_CHIAVE_CORRENTE = (idx + 1) % tot_chiavi
                    testo_out = getattr(risp, 'text', None)
                    if testo_out and testo_out.strip():
                        return testo_out.strip()
                    risposte_vuote += 1
                    if risposte_vuote >= 2:
                        return "ESCLUSO | SCONOSCIUTO | NESSUNA | -- | -- | -- | --"
                except Exception as e:
                    ultimo_errore = e
                    err_str = str(e).lower()
                    if any(x in err_str for x in ('404', 'not found', 'not supported', 'invalid argument')):
                        if mod in slot["modelli"]:
                            slot["modelli"].remove(mod)
                        continue
                    if any(x in err_str for x in ('per day', 'per_day', 'daily', 'requests per day')):
                        print(f"   {slot['id']} esaurita su {mod}. Ruoto chiave...")
                        if mod in slot["modelli"]:
                            slot["modelli"].remove(mod)
                        continue
                    if any(x in err_str for x in ('429', 'quota', 'exhausted', 'rate', '503', '504', 'deadline', 'unavailable', 'overloaded')):
                        break
        if not ha_capacita_gemini():
            break
        time.sleep(8 * giro)
    raise RuntimeError(f"Impossibile completare la richiesta Gemini: {ultimo_errore}")

def pulisci_nome_azienda(nome):
    if not nome:
        return ""
    pat = (
        r'(?i)\b(s\.r\.l\.|srl|s\.p\.a\.|spa|s\.n\.c\.|snc|s\.a\.s\.|sas|'
        r's\.r\.l\.s\.|srls|s\.c\.a\.r\.l\.|soc\.\s*coop\.|unipersonale|semplificata)\b'
    )
    return re.sub(r'\s+', ' ', re.sub(pat, '', nome)).strip().upper()

def pulisci_nome_per_linkedin(nome):
    base = pulisci_nome_azienda(nome)
    ridotto = re.sub(r'\s+', ' ', re.sub(r'(?i)\b(group|gruppo|holding)\b', '', base)).strip()
    return ridotto if len(ridotto) >= 3 else base

def estrai_dominio(testo_url):
    if not testo_url:
        return ""
    t = testo_url.strip().lower()
    return urlparse(t).netloc.replace('www.', '') if "://" in t else t.split('/')[0].replace('www.', '')

def email_valida(e):
    if not e or "@" not in e:
        return False
    e_low = e.strip().lower()
    if e_low in ("nessuna", "--"):
        return False
    falsi_positivi = (
        'pec@', '@pec', '.pec.', 'legalmail', 'postacert', 'certificata', 'sicurezzapostale',
        'telecompost', '@cert.', 'pcert.it', 'arubapec', 'nome@', 'esempio@', 'example@',
        'test@', 'tuamail@', 'tuaemail@', '@azienda.it', '@dominio.it', '@email.it',
        '@esempio.it', '@example.com', '@domain.com', '@info.com', '@info.it', '@manstar.org',
        '@xing.com', 'jimdoweb.com', 'webnode.it', 'webnode.page', 'sentry.io'
    )
    return not any(fp in e_low for fp in falsi_positivi)

def cerca_id_hubspot_contact(dominio, nome_azienda):
    if not hubspot_token:
        return None
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": pulisci_nome_azienda(nome_azienda)}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            results = res.json().get('results', [])
            if results:
                return results[0].get('id')
    except Exception:
        pass
    return None

def arricchisci_contatto_hubspot_esistente(
    contact_id, url_sito=None, email_generica=None, nome_dm=None, ruolo_dm=None,
    email_dm=None, settore=None, telefono=None, citta=None, regione=None, sostituisci_piva_tel=False
):
    if not hubspot_token or not contact_id:
        return "Già in HubSpot"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    campi = "email,hs_additional_emails,referente,phone,settore,city,state,website"
    try:
        res_get = requests.get(
            f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}?properties={campi}",
            headers=headers, timeout=10
        )
        if res_get.status_code != 200:
            return "Già in HubSpot"
        props_attuali = res_get.json().get("properties", {}) or {}
    except Exception:
        return "Già in HubSpot"

    aggiornamenti = {}
    if nome_dm and nome_dm != "SCONOSCIUTO":
        ruolo = ruolo_dm.upper() if (ruolo_dm and ruolo_dm != "NESSUNO") else ""
        nuovo_ref = f"{nome_dm.upper()} {ruolo}".strip()
        ref_attuale = (props_attuali.get("referente") or "").strip()
        if not ref_attuale or ref_attuale == "--":
            aggiornamenti["referente"] = nuovo_ref
        elif nome_dm.upper() not in ref_attuale.upper():
            aggiornamenti["referente"] = f"{ref_attuale} / {nuovo_ref}"

    if telefono and telefono != "--":
        tel_nuovo = telefono.strip()
        tel_attuale = (props_attuali.get("phone") or "").strip()
        cifre_nuovo = re.sub(r'\D', '', tel_nuovo)
        cifre_att = re.sub(r'\D', '', tel_attuale)
        cifre_att_11 = cifre_att[2:] if cifre_att.startswith('39') and len(cifre_att) == 13 else cifre_att
        if not tel_attuale or tel_attuale == "--" or sostituisci_piva_tel or is_partita_iva_italiana(cifre_att_11):
            aggiornamenti["phone"] = tel_nuovo
        elif cifre_nuovo and cifre_nuovo[-8:] not in cifre_att:
            aggiornamenti["phone"] = f"{tel_attuale} / {tel_nuovo}"

    email_attuale = (props_attuali.get("email") or "").strip().lower()
    add_attuali_str = (props_attuali.get("hs_additional_emails") or "").strip().lower()
    lista_add = [e.strip() for e in re.split(r'[;,]', add_attuali_str) if e.strip()]
    tutte_esistenti = set(lista_add + ([email_attuale] if email_attuale else []))

    for e_cand in [email_dm, email_generica]:
        if email_valida(e_cand):
            ec = e_cand.strip().lower()
            if ec not in tutte_esistenti:
                if not email_attuale:
                    email_attuale = ec
                    aggiornamenti["email"] = ec
                else:
                    lista_add.append(ec)
                tutte_esistenti.add(ec)

    if lista_add:
        nuova_str_add = ";".join(lista_add)
        if nuova_str_add != add_attuali_str:
            aggiornamenti["hs_additional_emails"] = nuova_str_add

    if settore and settore != "--" and not (props_attuali.get("settore") or "").strip():
        aggiornamenti["settore"] = settore.upper()
    if citta and citta != "--" and not (props_attuali.get("city") or "").strip():
        aggiornamenti["city"] = citta.upper()
    if regione and regione != "--" and not (props_attuali.get("state") or "").strip():
        aggiornamenti["state"] = regione.upper()
    if url_sito and not (props_attuali.get("website") or "").strip():
        aggiornamenti["website"] = url_sito

    if aggiornamenti:
        try:
            url_patch = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
            res_patch = requests.patch(url_patch, headers=headers, json={"properties": aggiornamenti}, timeout=10)
            if res_patch.status_code == 200:
                return "Già in HubSpot (Arricchito)"
            elif "hs_additional_emails" in aggiornamenti:
                del aggiornamenti["hs_additional_emails"]
                if aggiornamenti:
                    requests.patch(url_patch, headers=headers, json={"properties": aggiornamenti}, timeout=10)
                    return "Già in HubSpot (Arricchito)"
        except Exception:
            pass
    return "Già in HubSpot"

def crea_hubspot_contact(
    nome_azienda, url_sito, email_generica, nome_dm, ruolo_dm,
    email_dm, settore, telefono, citta, regione
):
    if not hubspot_token:
        return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    properties = {"firstname": nome_azienda.upper(), "company": nome_azienda.upper(), "website": url_sito}
    if settore and settore != "--":
        properties["settore"] = settore.upper()
    if telefono and telefono != "--":
        properties["phone"] = telefono.upper()
    if citta and citta != "--":
        properties["city"] = citta.upper()
    if regione and regione != "--":
        properties["state"] = regione.upper()
    if nome_dm and nome_dm != "SCONOSCIUTO":
        ruolo = ruolo_dm.upper() if ruolo_dm != "NESSUNO" else ""
        properties["referente"] = f"{nome_dm.upper()} {ruolo}".strip()

    email_primaria = email_dm if email_valida(email_dm) else (email_generica if email_valida(email_generica) else None)
    email_secondaria = email_generica if (email_primaria == email_dm and email_valida(email_generica)) else None
    if email_primaria:
        properties["email"] = email_primaria
        if email_secondaria and email_secondaria != email_primaria:
            properties["hs_additional_emails"] = email_secondaria

    try:
        res = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers=headers, json={"properties": properties}, timeout=10
        )
        if res.status_code in (200, 201):
            return "Inserito in HubSpot"
        errore = res.json().get("message", "Errore sconosciuto")
        match_id = re.search(r'Existing ID:\s*(\d+)', errore)
        if match_id:
            return arricchisci_contatto_hubspot_esistente(
                match_id.group(1), url_sito=url_sito, email_generica=email_generica,
                nome_dm=nome_dm, ruolo_dm=ruolo_dm, email_dm=email_dm,
                settore=settore, telefono=telefono, citta=citta, regione=regione
            )
        return f"Errore CRM: {errore}"
    except Exception:
        return "Errore CRM"

def cerca_dati_aziendali_osint(nome_azienda, dominio=""):
    if not serper_api_key or nome_azienda == "SCONOSCIUTO":
        return None, None
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    payload = json.dumps({"q": f'"{azienda_pulita}" {dominio} telefono contatti'.strip(), "gl": "it", "hl": "it"})
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    try:
        res = requests.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=10)
        if res.status_code == 200:
            data = res.json()
            telefono, indirizzo = None, None
            kg = data.get('knowledgeGraph', {})
            if kg:
                cand_kg = normalizza_telefono_outbound(kg.get('phoneNumber'))
                if cand_kg != "--":
                    telefono = cand_kg
                indirizzo = kg.get('address')
                if not telefono:
                    for key, val in (kg.get('attributes') or {}).items():
                        if 'telefon' in key.lower() or 'phone' in key.lower():
                            cand_at = normalizza_telefono_outbound(val)
                            if cand_at != "--":
                                telefono = cand_at
                                break
            if not telefono or not indirizzo:
                for place in data.get('places', []):
                    if not telefono and place.get('phoneNumber'):
                        cand_pl = normalizza_telefono_outbound(place.get('phoneNumber'))
                        if cand_pl != "--":
                            telefono = cand_pl
                    if not indirizzo and place.get('address'):
                        indirizzo = place.get('address')
                    if telefono and indirizzo:
                        break
            if not telefono:
                pat_tel = r'(?:\+39|0039)?[\s\.\-]?(?:0\d{1,3}|3\d{2})[\s\.\-\/]?[\d\s\.\-]{5,10}'
                for org in data.get('organic', [])[:5]:
                    snip = pulisci_testo_da_piva_e_fax(f"{org.get('title', '')} {org.get('snippet', '')}")
                    for cand_raw in re.findall(pat_tel, snip):
                        cand_norm = normalizza_telefono_outbound(cand_raw)
                        if cand_norm != "--":
                            telefono = cand_norm
                            break
                    if telefono:
                        break
            return telefono, indirizzo
    except Exception:
        pass
    return None, None

def cerca_decision_maker_osint(nome_azienda, dominio, email_generica):
    if not serper_api_key:
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
    url = "https://google.serper.dev/search"
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    azienda_linkedin = pulisci_nome_per_linkedin(nome_azienda)
    radice_dominio = dominio.split('.')[0] if dominio else ""
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}

    dominio_email = dominio
    if email_valida(email_generica):
        dom_estratto = email_generica.split("@")[-1].strip().lower()
        provider_gen = {
            'gmail.com', 'libero.it', 'virgilio.it', 'alice.it', 'tin.it', 'tiscali.it',
            'hotmail.com', 'hotmail.it', 'outlook.com', 'outlook.it', 'yahoo.com', 'yahoo.it',
            'icloud.com', 'email.it', 'azienda.it', 'dominio.it', 'esempio.it', 'example.com',
            'info.com', 'info.it', 'test.it', 'pcert.it', 'arubapec.it', 'legalmail.it',
            'pec.it', 'postecert.it', 'manstar.org', 'xing.com', 'jimdoweb.com', 'webnode.it', 'webnode.page'
        }
        escl_d = ('pec', 'cert', 'legalmail', 'jimdo', 'webnode', 'wixsite')
        if dom_estratto and dom_estratto not in provider_gen and not any(p in dom_estratto for p in escl_d):
            dominio_email = dom_estratto

    try:
        queries = [
            f'site:linkedin.com/in "{azienda_linkedin}" (Commerciale OR Vendite OR Sales OR Direttore OR HR OR CEO OR Titolare OR Amministratore OR Socio OR Owner)',
            f'site:linkedin.com/in ("{azienda_linkedin}" OR "{radice_dominio}" OR "{dominio}")',
            f'("{azienda_pulita}" OR "{dominio}") ("Direttore Commerciale" OR "Responsabile Vendite" OR "Responsabile Commerciale" OR "Amministratore Unico" OR "Amministratore Delegato" OR "Titolare" OR "CEO")'
        ]
        risultati = []
        for q in queries:
            res = requests.post(url, headers=headers, data=json.dumps({"q": q, "gl": "it", "hl": "it"}), timeout=10)
            if res.status_code == 200:
                risultati = res.json().get('organic', [])
            if risultati:
                break
        if not risultati:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"

        testo_risultati = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in risultati[:10]])
        prompt = f"""Sei un software CRM B2B per ricerca agenti di commercio. NON inserire disclaimer o intestazioni.
Analizza questi risultati pubblici per l'azienda '{azienda_pulita}' (dominio: {dominio}). Dominio email: '{dominio_email}'.
Individua UN referente reale seguendo questa priorita:
1. Coordinamento Rete Vendita: Direttore Commerciale, Responsabile Vendite, Sales Director, Head of Sales, Sales Manager, Export Manager.
2. HR: HR Manager, Responsabile Risorse Umane, Talent Acquisition.
3. Vertice: Amministratore Delegato, Amministratore Unico, CEO, Titolare, Presidente, Socio, Owner.
ESCLUSIONI: NON selezionare Area Manager, Capo Area, District Manager o Zone Manager. Preferisci sempre il Direttore Commerciale al CEO.
Costruisci email: nome.cognome@{dominio_email} (minuscolo, senza spazi o accenti).
Rispondi SU UNA SOLA RIGA senza intestazione: NOME COGNOME | RUOLO | EMAIL
Se assente scrivi SOLO: SCONOSCIUTO | NESSUNO | NESSUNA

Risultati:
{testo_risultati}"""

        testo_risp = chiama_gemini_con_fallback(prompt, pausa_iniziale=2)
        righe_dm = [r for r in testo_risp.splitlines() if "|" in r and "NOME COGNOME" not in r.upper()]
        riga_target = (righe_dm[0] if righe_dm else testo_risp).replace("*", "").replace("Nome:", "").replace("Ruolo:", "").replace("Email:", "")
        parti = riga_target.split('|')
        nome_dm = parti[0].strip() if len(parti) > 0 else "SCONOSCIUTO"
        ruolo_dm = parti[1].strip() if len(parti) > 1 else "NESSUNO"
        email_dm = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
        if "SCONOSCIUTO" in nome_dm.upper() or len(nome_dm) < 3 or " " not in nome_dm:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        return nome_dm, ruolo_dm, email_dm
    except Exception as e_dm:
        print(f"Errore referente per {azienda_pulita}: {e_dm}")
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"

def bonifica_link_scartati(worksheet_master, dati):
    modifiche_col_b, conteggio = [], 0
    for i in range(1, len(dati)):
        riga = dati[i]
        url_val = riga[1].strip() if len(riga) > 1 else ""
        esito_val = riga[3].strip().upper() if len(riga) > 3 else ""
        if esito_val and "AGENTE" not in esito_val and "://" in url_val:
            modifiche_col_b.append([estrai_dominio(url_val)])
            conteggio += 1
        else:
            modifiche_col_b.append([url_val])
    if conteggio > 0:
        print(f"Bonifica anti-phishing: disinnesco {conteggio} URL scartati...")
        worksheet_master.update(values=modifiche_col_b, range_name=f"B2:B{len(dati)}")
        time.sleep(1.5)

def integra_referenti_e_telefoni_mancanti(worksheet_assistente, dati_prospect):
    print("Verifica ultimi 30 contatti in 'Nuovi Prospect' (Referente + Telefono Outbound)...")
    tot_righe = len(dati_prospect)
    for idx in range(max(1, tot_righe - 30), tot_righe):
        if not ha_capacita_gemini():
            break
        riga_p = dati_prospect[idx]
        num_riga_sheet = idx + 1
        nome_az = riga_p[0].strip() if len(riga_p) > 0 else ""
        url_az = riga_p[1].strip() if len(riga_p) > 1 else ""
        email_az = riga_p[5].strip().lower() if len(riga_p) > 5 else ""
        referente_att = riga_p[6].strip() if len(riga_p) > 6 else ""
        telefono_att = riga_p[9].strip() if len(riga_p) > 9 else ""

        if not nome_az or not url_az:
            continue
        dominio_az = estrai_dominio(url_az)
        if any(agg in dominio_az for agg in AGGREGATORI_DA_BLOCCARE):
            continue

        cifre_att = re.sub(r'\D', '', telefono_att)
        if cifre_att.startswith('39') and len(cifre_att) == 13:
            cifre_att = cifre_att[2:]
        era_piva = is_partita_iva_italiana(cifre_att)
        manca_ref = (not referente_att)
        manca_tel = (not telefono_att or telefono_att == "--" or era_piva)

        if manca_ref or manca_tel:
            nome_dm, ruolo_dm, email_dm = "SCONOSCIUTO", "NESSUNO", "NESSUNA"
            if manca_ref:
                nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_az, dominio_az, email_az)
                if nome_dm != "SCONOSCIUTO":
                    ref_c = f"{nome_dm.upper()} {ruolo_dm.upper()}".strip()
                    em_f = email_dm if email_valida(email_dm) else ""
                    worksheet_assistente.update(values=[[ref_c, em_f]], range_name=f"G{num_riga_sheet}:H{num_riga_sheet}")
                else:
                    worksheet_assistente.update(values=[["--", "NESSUNA"]], range_name=f"G{num_riga_sheet}:H{num_riga_sheet}")

            tel_trovato = None
            if manca_tel:
                tel_trovato, _ = cerca_dati_aziendali_osint(nome_az, dominio_az)
                if not tel_trovato:
                    try:
                        html_p = scarica_pagina_sicura(url_az, timeout_sec=7)
                        soup_p = BeautifulSoup(html_p, 'html.parser')
                        tel_h = estrai_telefoni_da_html(html_p, soup_p)
                        if tel_h == "--":
                            tel_h = cerca_telefono_in_pagina_contatti(url_az, soup_p)
                        if tel_h != "--":
                            tel_trovato = tel_h
                    except Exception:
                        pass
                if tel_trovato:
                    worksheet_assistente.update(values=[[tel_trovato]], range_name=f"J{num_riga_sheet}")
                    print(f"Telefono valido aggiornato per {nome_az}: {tel_trovato}")
                elif era_piva:
                    worksheet_assistente.update(values=[["--"]], range_name=f"J{num_riga_sheet}")
                    print(f"Rimossa falsa P.IVA dal telefono per {nome_az}")

            if nome_dm != "SCONOSCIUTO" or tel_trovato:
                contact_id = cerca_id_hubspot_contact(dominio_az, nome_az)
                if contact_id:
                    arricchisci_contatto_hubspot_esistente(
                        contact_id, url_sito=url_az, email_generica=email_az,
                        nome_dm=nome_dm, ruolo_dm=ruolo_dm,
                        email_dm=(email_dm if email_valida(email_dm) else None),
                        telefono=tel_trovato, sostituisci_piva_tel=era_piva
                    )
            time.sleep(1.0)

def main():
    url_foglio = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0"
    try:
        sh = gc.open_by_url(url_foglio)
        worksheet_master = sh.sheet1
        worksheet_assistente = sh.worksheet("Nuovi Prospect")
    except Exception as e_open:
        print(f"Errore apertura foglio Google: {e_open}")
        return

    dati = worksheet_master.get_all_values()
    dati_prospect = worksheet_assistente.get_all_values()
    data_odierna = datetime.now().strftime('%d/%m/%Y')

    bonifica_link_scartati(worksheet_master, dati)
    integra_referenti_e_telefoni_mancanti(worksheet_assistente, dati_prospect)

    aziende_gia_in_prospect, domini_gia_in_prospect = set(), set()
    for r_p in dati_prospect[1:]:
        if len(r_p) > 0 and r_p[0].strip():
            aziende_gia_in_prospect.add(pulisci_nome_azienda(r_p[0]))
        if len(r_p) > 1 and r_p[1].strip():
            dom_p = estrai_dominio(r_p[1])
            if dom_p:
                domini_gia_in_prospect.add(dom_p)

    for i in range(1, len(dati)):
        if not ha_capacita_gemini():
            print("Tutte le chiavi API hanno esaurito la quota giornaliera. Stop pulito.")
            break
        riga = dati[i]
        if len(riga) < 2:
            continue
        url_sito = riga[1].strip()
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        if url_sito and not esito_attuale:
            numero_riga = i + 1
            dominio = estrai_dominio(url_sito)
            if "://" not in url_sito:
                url_sito = f"https://www.{dominio}"
            url_low = url_sito.lower()

            if any(agg in dominio for agg in AGGREGATORI_DA_BLOCCARE) or any(p_agg in url_low for p_agg in PATH_AGGREGATORI_DA_BLOCCARE):
                print(f"Salto riga {numero_riga} ({dominio}): portale/notizie escluso.")
                worksheet_master.update(values=[[dominio, "Portale / Directory", "ESCLUSO", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                time.sleep(0.8)
                continue

            if dominio in domini_gia_in_prospect:
                print(f"Salto riga {numero_riga} ({dominio}): già in Nuovi Prospect.")
                worksheet_master.update(values=[[dominio, "Già in Nuovi Prospect", "DUPLICATO", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                time.sleep(0.8)
                continue

            print(f"Processo riga {numero_riga}: {url_sito}")
            try:
                html_pagina = scarica_pagina_sicura(url_sito, timeout_sec=10)
            except Exception as e_web:
                print(f"Sito non raggiungibile ({url_sito}): {e_web}")
                worksheet_master.update(values=[[dominio, "Sito non raggiungibile", "ERRORE", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                time.sleep(0.8)
                continue

            try:
                soup = BeautifulSoup(html_pagina, 'html.parser')
                titolo_raw = soup.title.string.strip() if soup.title and soup.title.string else "Sito Aziendale"
                titolo = re.sub(r'\s+', ' ', titolo_raw)[:100]
                tel_da_html = estrai_telefoni_da_html(html_pagina, soup)

                for tag in soup(["script", "style", "nav", "svg", "noscript"]):
                    tag.decompose()
                testo = soup.get_text(separator=' ', strip=True)[:4500]
                testo_check = f"{titolo} {url_sito} {testo}".lower()

                if any(ea in testo_check for ea in ('agenti ai', 'agente ai', 'agenti digitali', 'agentic ', 'intelligenza artificiale')) and 'enasarco' not in testo_check:
                    worksheet_master.update(values=[[dominio, titolo, "ESCLUSO", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                    print(f"   Riga {numero_riga} esclusa a costo zero (Agenti AI/Software): {dominio}")
                    time.sleep(0.8)
                    continue

                if not any(kw in testo_check for kw in PAROLE_CHIAVE_AGENTE):
                    worksheet_master.update(values=[[dominio, titolo, "ESCLUSO", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                    print(f"   Riga {numero_riga} esclusa a costo zero (nessun termine agente): {dominio}")
                    time.sleep(0.8)
                    continue

                emails_trovate = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html_pagina)
                escl_file = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css', 'sentry.io')
                emails_pulite = list(set([e.lower() for e in emails_trovate if not e.lower().endswith(escl_file) and email_valida(e)]))
                email_suggerita = emails_pulite[0] if emails_pulite else "NESSUNA"

                prompt_web = f"""Analizza questa pagina web per una societa di ricerca e selezione agenti di commercio.
URL: {url_sito} | Dominio: {dominio} | Titolo: {titolo}

Estrai 7 campi separati da |:
1. ESITO: Scrivi UNICAMENTE una di queste tre parole esatte: AGENTE oppure DIPENDENTE oppure ESCLUSO.
Scrivi AGENTE SOLO se la pagina appartiene al sito ufficiale di un'azienda italiana/operante in Italia e contiene un annuncio o invito ESPLICITO a candidarsi per diventare Agente di Commercio, Rappresentante, Venditore a P.IVA o Procacciatore.
Scrivi ESCLUSO se:
- Non e il sito ufficiale dell'azienda mandante (portali annunci, directory, blog, studi legali/commercialisti, associazioni).
- Homepage, Chi siamo, Prodotti, News o Contatti senza ricerca aperta di agenti/venditori.
- Parla di Agenti AI / Intelligenza Artificiale.
- Produttori esteri senza sede in Italia o multinazionali quotate (cerchiamo solo PMI italiane).
- Pagina Rete vendita/Distributori per clienti finali senza selezione agenti.
- Vendita diretta a domicilio / network marketing.
- Immobiliare, assicurazioni, finanziarie/mediazione creditizia, noleggio auto, recupero anni scolastici, tour operator.
- Contratti Luce, Gas, Energia, Fotovoltaico residenziale, Telefonia, Concessionarie auto.
- Agenzie selezione agenti o software CRM per agenti.
2. NOME_AZIENDA: Vero nome azienda mandante (se ESCLUSO scrivi SCONOSCIUTO).
3. EMAIL: Email reale azienda (suggerita: {email_suggerita}; NO PEC; se assente NESSUNA).
4. SETTORE: Settore aziendale sintetico (o "--").
5. TELEFONO: Telefono fisso/mobile aziendale (suggerito: {tel_da_html}; MAI Partita IVA o FAX; se assente "--").
6. CITTA: Citta sede con sigla provincia se non capoluogo, es. BUSTO ARSIZIO VA (o "--").
7. REGIONE: Regione italiana (o "--").

IMPORTANTE: Rispondi SU UNA SOLA RIGA con i 7 valori separati da | SENZA scrivere intestazioni.
Esempio: AGENTE | ROSSI MECCANICA SRL | info@rossi.it | MECCANICA | +39 0331123456 | BUSTO ARSIZIO VA | LOMBARDIA

Testo: {testo}"""

                testo_risposta = chiama_gemini_con_fallback(prompt_web, pausa_iniziale=3)
                parti = parse_risposta_sito(testo_risposta) or ["ESCLUSO", "SCONOSCIUTO", "NESSUNA", "--", "--", "--", "--"]

                esito, nome_reale = parti[0], parti[1].strip()
                email = parti[2].strip().lower()
                if not email_valida(email):
                    email = email_suggerita if email_valida(email_suggerita) else "NESSUNA"
                settore = parti[3].strip()
                tel_ia = normalizza_telefono_outbound(parti[4].strip())
                telefono_sito = tel_ia if tel_ia != "--" else tel_da_html
                citta_sito, regione_sito = parti[5].strip(), parti[6].strip()

                if esito != "AGENTE":
                    worksheet_master.update(values=[[dominio, titolo, esito, data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                    print(f"   Riga {numero_riga} classificata: {esito} ({dominio})")
                else:
                    worksheet_master.update(values=[[titolo, "AGENTE", data_odierna]], range_name=f"C{numero_riga}:E{numero_riga}")
                    print(f"   Riga {numero_riga} classificata: AGENTE -> {nome_reale}")
                time.sleep(0.8)

                if esito == "AGENTE":
                    nome_pulito = pulisci_nome_azienda(nome_reale)
                    if (nome_pulito and nome_pulito in aziende_gia_in_prospect) or (dominio in domini_gia_in_prospect):
                        print(f"   Salto {nome_reale}: già in Nuovi Prospect.")
                        continue

                    nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_reale, dominio, email)
                    tel_google, ind_google = cerca_dati_aziendali_osint(nome_reale, dominio)
                    telefono_finale = tel_google if tel_google else telefono_sito

                    if not telefono_finale or telefono_finale == "--":
                        tel_cont = cerca_telefono_in_pagina_contatti(url_sito, soup)
                        if tel_cont != "--":
                            telefono_finale = tel_cont

                    citta_finale, regione_finale = citta_sito, regione_sito
                    if ind_google:
                        citta_g, reg_g = estrai_citta_regione_locale(ind_google)
                        if citta_g != "--":
                            citta_finale = citta_g
                        if reg_g != "--":
                            regione_finale = reg_g

                    contact_id_esistente = cerca_id_hubspot_contact(dominio, nome_reale)
                    if contact_id_esistente:
                        stato_crm = arricchisci_contatto_hubspot_esistente(
                            contact_id_esistente, url_sito=url_sito, email_generica=email,
                            nome_dm=nome_dm, ruolo_dm=ruolo_dm, email_dm=email_dm,
                            settore=settore, telefono=telefono_finale, citta=citta_finale, regione=regione_finale
                        )
                    else:
                        stato_crm = crea_hubspot_contact(
                            nome_reale, url_sito, email, nome_dm, ruolo_dm, email_dm,
                            settore, telefono_finale, citta_finale, regione_finale
                        )

                    referente_completo = f"{nome_dm.upper()} {ruolo_dm.upper()}".strip() if nome_dm != "SCONOSCIUTO" else "--"
                    email_referente_finale = email_dm if email_valida(email_dm) else "NESSUNA"
                    email_azienda_finale = email if email_valida(email) else ""

                    nuova_riga = [
                        nome_reale.upper(), url_sito, titolo, "AGENTE", stato_crm,
                        email_azienda_finale, referente_completo, email_referente_finale,
                        data_odierna, telefono_finale if telefono_finale else "--"
                    ]
                    worksheet_assistente.append_row(nuova_riga)
                    print(f"   Prospect salvato con Telefono Outbound: {telefono_finale}")

                    if nome_pulito:
                        aziende_gia_in_prospect.add(nome_pulito)
                    domini_gia_in_prospect.add(dominio)

            except Exception as e_ia:
                if "QUOTA_GIORNALIERA_ESAURITA" in str(e_ia):
                    print("Quota giornaliera terminata su tutte le chiavi. Ripartirà al prossimo avvio.")
                    break
                print(f"Errore IA su riga {numero_riga} ({url_sito}): {e_ia}. Riga lasciata in coda.")
                time.sleep(2)

if __name__ == "__main__":
    main()
