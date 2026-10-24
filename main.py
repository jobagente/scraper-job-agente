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
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse
from datetime import datetime

# Forza la stampa immediata nei log di GitHub Actions
sys.stdout.reconfigure(line_buffering=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

creds_json = os.environ.get('GCP_CREDENTIALS')
gemini_api_key = os.environ.get('GEMINI_API_KEY')
hubspot_token = os.environ.get('HUBSPOT_ACCESS_TOKEN')
serper_api_key = os.environ.get('SERPER_API_KEY')

creds_dict = json.loads(creds_json)
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
client = genai.Client(api_key=gemini_api_key)

HEADERS_BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'
}

def pulisci_nome_azienda(nome):
    if not nome: return ""
    pulito = re.sub(r'(?i)\b(s\.r\.l\.|srl|s\.p\.a\.|spa|s\.n\.c\.|snc|s\.a\.s\.|sas|s\.r\.l\.s\.|srls|s\.c\.a\.r\.l\.|soc\.\s*coop\.|unipersonale|semplificata)\b', '', nome)
    return re.sub(r'\s+', ' ', pulito).strip().upper()

def pulisci_nome_per_linkedin(nome):
    """Rimuove anche suffissi generici come GROUP o HOLDING che spesso non compaiono nei profili LinkedIn dei dipendenti."""
    base = pulisci_nome_azienda(nome)
    ridotto = re.sub(r'(?i)\b(group|gruppo|holding)\b', '', base)
    ridotto = re.sub(r'\s+', ' ', ridotto).strip()
    return ridotto if len(ridotto) >= 3 else base

def estrai_dominio(testo_url):
    if not testo_url: return ""
    t = testo_url.strip().lower()
    if "://" in t:
        return urlparse(t).netloc.replace('www.', '')
    return t.split('/')[0].replace('www.', '')

def email_valida(e):
    """Verifica che l'email sia reale e non un segnaposto/PEC."""
    if not e or "@" not in e: return False
    e_low = e.strip().lower()
    if e_low in ("nessuna", "--"): return False
    falsi_positivi = [
        'pec@', '@pec', '.pec.', 'legalmail', 'postacert', 'certificata',
        'sicurezzapostale', 'telecompost', '@cert.', 'pcert.it', 'arubapec',
        'nome@', 'esempio@', 'example@', 'test@', 'tuamail@', 'tuaemail@',
        '@azienda.it', '@dominio.it', '@email.it', '@esempio.it', '@example.com', '@domain.com'
    ]
    return not any(fp in e_low for fp in falsi_positivi)

def cerca_id_hubspot_contact(dominio, nome_azienda):
    if not hubspot_token: return None
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": azienda_pulita}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            results = res.json().get('results', [])
            if results:
                return results[0].get('id')
    except: pass
    return None

def arricchisci_contatto_hubspot_esistente(contact_id, url_sito=None, email_generica=None, nome_dm=None, ruolo_dm=None, email_dm=None, settore=None, telefono=None, citta=None, regione=None):
    """
    Legge i dati già presenti nella scheda HubSpot e AGGIUNGE i nuovi dati (referente, telefono, email)
    SENZA MAI cancellare o sovrascrivere le informazioni già presenti.
    """
    if not hubspot_token or not contact_id: return "Già in HubSpot"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    campi = "email,hs_additional_emails,referente,phone,settore,city,state,website"
    url_get = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}?properties={campi}"
    
    try:
        res_get = requests.get(url_get, headers=headers, timeout=15)
        if res_get.status_code != 200:
            return "Già in HubSpot"
        props_attuali = res_get.json().get("properties", {}) or {}
    except Exception:
        return "Già in HubSpot"

    aggiornamenti = {}

    # 1. REFERENTE: aggiunge il nuovo referente senza cancellare quello esistente
    if nome_dm and nome_dm != "SCONOSCIUTO":
        ruolo = ruolo_dm.upper() if (ruolo_dm and ruolo_dm != "NESSUNO") else ""
        nuovo_ref = f"{nome_dm.upper()} {ruolo}".strip()
        ref_attuale = (props_attuali.get("referente") or "").strip()
        
        if not ref_attuale or ref_attuale == "--":
            aggiornamenti["referente"] = nuovo_ref
        elif nome_dm.upper() not in ref_attuale.upper():
            aggiornamenti["referente"] = f"{ref_attuale} / {nuovo_ref}"

    # 2. TELEFONO: se manca lo inserisce; se c'è già un numero diverso, accoda il nuovo con " / "
    if telefono and telefono != "--":
        tel_nuovo = telefono.strip()
        tel_attuale = (props_attuali.get("phone") or "").strip()
        cifre_nuovo = re.sub(r'\D', '', tel_nuovo)
        cifre_attuale = re.sub(r'\D', '', tel_attuale)
        
        if not tel_attuale or tel_attuale == "--":
            aggiornamenti["phone"] = tel_nuovo
        elif cifre_nuovo and cifre_nuovo not in cifre_attuale:
            aggiornamenti["phone"] = f"{tel_attuale} / {tel_nuovo}"

    # 3. EMAIL: mantiene SEMPRE l'email primaria esistente e aggiunge le nuove in hs_additional_emails
    email_attuale = (props_attuali.get("email") or "").strip().lower()
    add_attuali_str = (props_attuali.get("hs_additional_emails") or "").strip().lower()
    lista_add = [e.strip() for e in re.split(r'[;,]', add_attuali_str) if e.strip()]
    
    tutte_esistenti = set()
    if email_attuale:
        tutte_esistenti.add(email_attuale)
    tutte_esistenti.update(lista_add)

    nuove_email_da_valutare = []
    if email_valida(email_dm):
        nuove_email_da_valutare.append(email_dm.strip().lower())
    if email_valida(email_generica):
        nuove_email_da_valutare.append(email_generica.strip().lower())

    for e_cand in nuove_email_da_valutare:
        if e_cand not in tutte_esistenti:
            if not email_attuale:
                # Il contatto su HubSpot era completamente privo di email primaria
                email_attuale = e_cand
                aggiornamenti["email"] = e_cand
                tutte_esistenti.add(e_cand)
            else:
                # C'è già un'email primaria: aggiunge la nuova tra le email secondarie
                lista_add.append(e_cand)
                tutte_esistenti.add(e_cand)

    if lista_add:
        nuova_str_add = ";".join(lista_add)
        if nuova_str_add != add_attuali_str:
            aggiornamenti["hs_additional_emails"] = nuova_str_add

    # 4. CAMPI COMPLEMENTARI (Settore, Città, Regione, Website): compilati solo se vuoti su HubSpot
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
            res_patch = requests.patch(url_patch, headers=headers, json={"properties": aggiornamenti}, timeout=15)
            if res_patch.status_code == 200:
                return "Già in HubSpot (Arricchito)"
            elif "hs_additional_emails" in aggiornamenti:
                # Se una delle email aggiuntive appartiene già a un'altra scheda in HubSpot, salva comunque referente e telefono
                del aggiornamenti["hs_additional_emails"]
                if aggiornamenti:
                    requests.patch(url_patch, headers=headers, json={"properties": aggiornamenti}, timeout=15)
                    return "Già in HubSpot (Arricchito)"
        except Exception:
            pass

    return "Già in HubSpot"

def crea_hubspot_contact(nome_azienda, url_sito, email_generica, nome_dm, ruolo_dm, email_dm, settore, telefono, citta, regione):
    if not hubspot_token: return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    properties = {
        "firstname": nome_azienda.upper(),
        "company": nome_azienda.upper(),
        "website": url_sito
    }
    
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
        url_cont = "https://api.hubapi.com/crm/v3/objects/contacts"
        res = requests.post(url_cont, headers=headers, json={"properties": properties}, timeout=15)
        if res.status_code in (200, 201):
            return "Inserito in HubSpot"
        else:
            errore = res.json().get("message", "Errore sconosciuto")
            return f"Errore CRM: {errore}"
    except Exception as e:
        return f"Errore CRM"

def cerca_dati_aziendali_osint(nome_azienda):
    if not serper_api_key or nome_azienda == "SCONOSCIUTO": return None, None
        
    url = "https://google.serper.dev/search"
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    
    payload = json.dumps({"q": azienda_pulita, "gl": "it", "hl": "it"})
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=15)
        if res.status_code == 200:
            data = res.json()
            telefono = None
            indirizzo = None
            
            kg = data.get('knowledgeGraph', {})
            if kg:
                telefono = kg.get('phoneNumber')
                indirizzo = kg.get('address')
                
                if not telefono:
                    attr = kg.get('attributes', {})
                    for key, val in attr.items():
                        if 'telefon' in key.lower() or 'phone' in key.lower():
                            telefono = val
                            break
            
            if not telefono or not indirizzo:
                places = data.get('places', [])
                for place in places:
                    if not telefono and place.get('phoneNumber'):
                        telefono = place.get('phoneNumber')
                    if not indirizzo and place.get('address'):
                        indirizzo = place.get('address')
                    if telefono and indirizzo:
                        break
                        
            return telefono, indirizzo
    except Exception: pass
    return None, None

def formatta_indirizzo_osint(indirizzo):
    if not indirizzo: return "--", "--"
    prompt = f"Estrai Città (con sigla provincia se non è capoluogo) e Regione da questo indirizzo: '{indirizzo}'.\nRispondi ESATTAMENTE su una sola riga nel formato: CITTA | REGIONE\nSe manca un dato scrivi --."
    try:
        time.sleep(3)
        risposta = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        parti = risposta.text.strip().replace("*", "").split('|')
        citta = parti[0].strip().upper() if len(parti) > 0 else "--"
        regione = parti[1].strip().upper() if len(parti) > 1 else "--"
        return citta, regione
    except:
        return "--", "--"

def cerca_decision_maker_osint(nome_azienda, dominio, email_generica):
    if not serper_api_key: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
    url = "https://google.serper.dev/search"
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    azienda_linkedin = pulisci_nome_per_linkedin(nome_azienda)
    radice_dominio = dominio.split('.')[0] if dominio else ""
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    dominio_email = dominio
    if email_valida(email_generica):
        dom_estratto = email_generica.split("@")[-1].strip().lower()
        provider_generici = {
            'gmail.com', 'libero.it', 'virgilio.it', 'alice.it', 'tin.it', 'tiscali.it', 
            'hotmail.com', 'hotmail.it', 'outlook.com', 'outlook.it', 'yahoo.com', 'yahoo.it', 
            'icloud.com', 'email.it', 'azienda.it', 'dominio.it', 'esempio.it', 'example.com', 
            'test.it', 'pcert.it', 'arubapec.it', 'legalmail.it', 'pec.it', 'postecert.it'
        }
        if dom_estratto and dom_estratto not in provider_generici and not any(p in dom_estratto for p in ['pec', 'cert', 'legalmail']):
            dominio_email = dom_estratto
    
    try:
        risultati = []
        
        # LIVELLO 1: Ricerca su tutto linkedin.com/in con nome pulito (senza "Group/Srl") e ruoli target
        q1 = f'site:linkedin.com/in "{azienda_linkedin}" (Commerciale OR Vendite OR Sales OR Direttore OR HR OR CEO OR Titolare OR Amministratore OR Socio OR Owner)'
        res1 = requests.post(url, headers=headers, data=json.dumps({"q": q1, "gl": "it", "hl": "it"}), timeout=15)
        if res1.status_code == 200:
            risultati = res1.json().get('organic', [])
            
        # LIVELLO 2: Ricerca più ampia su LinkedIn per nome base o dominio (es. "cigiservice" o "rrmgroup")
        if not risultati:
            q2 = f'site:linkedin.com/in ("{azienda_linkedin}" OR "{radice_dominio}" OR "{dominio}")'
            res2 = requests.post(url, headers=headers, data=json.dumps({"q": q2, "gl": "it", "hl": "it"}), timeout=15)
            if res2.status_code == 200:
                risultati = res2.json().get('organic', [])
                
        # LIVELLO 3: Se l'azienda è una PMI non presente su LinkedIn, cerca sul web pubblico (sito aziendale / dati camerali)
        if not risultati:
            q3 = f'("{azienda_pulita}" OR "{dominio}") ("Direttore Commerciale" OR "Responsabile Vendite" OR "Responsabile Commerciale" OR "Amministratore Unico" OR "Amministratore Delegato" OR "Titolare" OR "CEO")'
            res3 = requests.post(url, headers=headers, data=json.dumps({"q": q3, "gl": "it", "hl": "it"}), timeout=15)
            if res3.status_code == 200:
                risultati = res3.json().get('organic', [])
                
        if not risultati:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        testo_risultati = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in risultati[:10]])
        
        prompt = f"""
        Sei un software CRM automatizzato per l'analisi di dati pubblici aziendali B2B per ricerca agenti di commercio.
        È cruciale per il sistema che tu NON inserisca mai disclaimer, avvisi sulla privacy, avvertenze o scuse.
        Analizza questi risultati pubblici trovati su Google/LinkedIn per l'azienda '{azienda_pulita}' (dominio: {dominio}).
        Dominio aziendale per costruire l'email: '{dominio_email}'
        
        OBIETTIVO STRATEGICO:
        Individua il nome e cognome di UN referente reale dell'azienda seguendo QUESTA SCALA DI PRIORITÀ:
        1. PRIORITÀ 1 (ASSOLUTA - Coordinamento Rete Vendita): Direttore Commerciale, Responsabile Vendite, Sales Director, Direttore Vendite, Head of Sales, Responsabile Commerciale, Sales Manager, Export Manager.
        2. PRIORITÀ 2 (HR / Risorse Umane): HR Manager, Responsabile Risorse Umane, Talent Acquisition, Direttore HR, Recruiter interno.
        3. PRIORITÀ 3 (Vertice aziendale / Proprietà): Amministratore Delegato, Amministratore Unico, CEO, Titolare, Presidente, Fondatore, Socio, Owner, Amministratore.
        
        REGOLE ED ESCLUSIONI:
        - NON SELEZIONARE "Area Manager", "Capo Area", "District Manager" o "Zone Manager".
        - Se individui sia un Direttore Commerciale/Responsabile Vendite sia un CEO/Titolare, scegli il Direttore Commerciale/Responsabile Vendite.
        - Assicurati che sia il nome e cognome di una persona fisica (non il nome di un'azienda o di una scuola).
        
        COSTRUISCI l'email diretta:
        nome.cognome@{dominio_email} (tutto minuscolo, senza spazi, rimuovi accenti).
        
        REGOLE DI RISPOSTA:
        - Rispondi ESATTAMENTE su una sola riga usando il separatore |.
        - Formato: NOME COGNOME | RUOLO | EMAIL
        - NON aggiungere altro testo, prefissi, spiegazioni o disclaimer. Se non trovi nessuna persona fisica chiara scrivi SOLO: SCONOSCIUTO | NESSUNO | NESSUNA
        - Esempio di risposta corretta: Marco Rossi | DIRETTORE COMMERCIALE | marco.rossi@{dominio_email}
        
        Risultati trovati:
        {testo_risultati}
        """
        
        time.sleep(5)
        for tentativo in range(2):
            try:
                risposta = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                testo_pulito = risposta.text.strip().replace("*", "").replace("Nome:", "").replace("Ruolo:", "").replace("Email:", "")
                parti = testo_pulito.split('|')
                
                nome_dm = parti[0].strip() if len(parti) > 0 else "SCONOSCIUTO"
                ruolo_dm = parti[1].strip() if len(parti) > 1 else "NESSUNO"
                email_dm = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
                
                if "SCONOSCIUTO" in nome_dm.upper() or len(nome_dm) < 3 or " " not in nome_dm:
                    return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
                    
                return nome_dm, ruolo_dm, email_dm
            except Exception as e_dm:
                if tentativo == 0:
                    time.sleep(15)
                else:
                    print(f"⚠️ Errore Gemini su referente per {azienda_pulita}: {e_dm}")
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
    except Exception as e:
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"

# =======================================================
# BONIFICA ANTI-PHISHING GOOGLE DRIVE (DISINNESCO URL SCARTATI)
# =======================================================
def bonifica_link_scartati(worksheet_master, dati):
    modifiche_col_b = []
    conteggio_bonificati = 0
    for i in range(1, len(dati)):
        riga = dati[i]
        url_val = riga[1].strip() if len(riga) > 1 else ""
        esito_val = riga[3].strip().upper() if len(riga) > 3 else ""
        
        if esito_val and "AGENTE" not in esito_val and "://" in url_val:
            dom_pulito = estrai_dominio(url_val)
            modifiche_col_b.append([dom_pulito])
            conteggio_bonificati += 1
        else:
            modifiche_col_b.append([url_val])
            
    if conteggio_bonificati > 0:
        print(f"🛡️ Bonifica anti-phishing: disinnesco {conteggio_bonificati} URL scartati in Foglio1...")
        worksheet_master.update(values=modifiche_col_b, range_name=f"B2:B{len(dati)}")
        time.sleep(2)

# =======================================================
# FUNZIONE DI INTEGRAZIONE AUTOMATICA CONTATTI SENZA REFERENTE (ULTIMI 20)
# =======================================================
def integra_referenti_mancanti(worksheet_assistente, dati_prospect):
    print("Verifica ultimi 20 contatti in 'Nuovi Prospect' con referente mancante...")
    tot_righe = len(dati_prospect)
    inizio_controllo = max(1, tot_righe - 20)
    
    for idx in range(inizio_controllo, tot_righe):
        riga_p = dati_prospect[idx]
        num_riga_sheet = idx + 1
        
        nome_az = riga_p[0].strip() if len(riga_p) > 0 else ""
        url_az = riga_p[1].strip() if len(riga_p) > 1 else ""
        email_az = riga_p[5].strip().lower() if len(riga_p) > 5 else ""
        referente_att = riga_p[6].strip() if len(riga_p) > 6 else ""
        
        if nome_az and url_az and not referente_att:
            dominio_az = estrai_dominio(url_az)
            print(f"🔄 Integrazione referente mancante per riga {num_riga_sheet}: {nome_az} ({dominio_az})")
            
            nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_az, dominio_az, email_az)
            
            if nome_dm != "SCONOSCIUTO":
                ref_completo = f"{nome_dm.upper()} {ruolo_dm.upper()}".strip()
                email_ref_finale = email_dm if email_valida(email_dm) else ""
                
                worksheet_assistente.update(values=[[ref_completo, email_ref_finale]], range_name=f"G{num_riga_sheet}:H{num_riga_sheet}")
                
                contact_id = cerca_id_hubspot_contact(dominio_az, nome_az)
                if contact_id:
                    arricchisci_contatto_hubspot_esistente(
                        contact_id, url_sito=url_az, email_generica=email_az,
                        nome_dm=nome_dm, ruolo_dm=ruolo_dm, email_dm=email_ref_finale
                    )
                    
                print(f"✅ Integrato con successo: {ref_completo} | {email_ref_finale}")
                time.sleep(2)
            else:
                worksheet_assistente.update(values=[["--", "NESSUNA"]], range_name=f"G{num_riga_sheet}:H{num_riga_sheet}")
                print(f"ℹ️ Nessun profilo LinkedIn pubblico trovato per {nome_az}.")
                time.sleep(1.5)

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet_master = sh.sheet1
        worksheet_assistente = sh.worksheet("Nuovi Prospect")
    except Exception as e: return

    dati = worksheet_master.get_all_values()
    dati_prospect = worksheet_assistente.get_all_values()
    data_odierna = datetime.now().strftime('%d/%m/%Y')
    
    # 0. BONIFICA AUTOMATICA DEI LINK SCARTATI (ANTI-AVVISO PHISHING GOOGLE DRIVE)
    bonifica_link_scartati(worksheet_master, dati)
    
    # 1. INTEGRA GLI ULTIMI 20 CONTATTI SENZA REFERENTE (FOGLIO + HUBSPOT)
    integra_referenti_mancanti(worksheet_assistente, dati_prospect)
    
    # 2. CARICAMENTO STORICO "NUOVI PROSPECT" ANTI-DOPPIONI
    aziende_gia_in_prospect = set()
    domini_gia_in_prospect = set()
    for r_p in dati_prospect[1:]:
        if len(r_p) > 0 and r_p[0].strip():
            aziende_gia_in_prospect.add(pulisci_nome_azienda(r_p[0]))
        if len(r_p) > 1 and r_p[1].strip():
            dom_p = estrai_dominio(r_p[1])
            if dom_p:
                domini_gia_in_prospect.add(dom_p)
    
    # 3. ANALISI NUOVE RIGHE DA FOGLIO1
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2: continue
            
        url_sito = riga[1].strip()
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        if url_sito and not esito_attuale:
            numero_riga = i + 1
            dominio = estrai_dominio(url_sito)
            
            if dominio in domini_gia_in_prospect:
                print(f"Salto riga {numero_riga} ({dominio}): dominio già presente in Nuovi Prospect.")
                worksheet_master.update(values=[[dominio, "Già in Nuovi Prospect", "DUPLICATO", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                time.sleep(1.5)
                continue

            print(f"Processo riga {numero_riga}: {url_sito}")
            
            try:
                res_web = requests.get(url_sito, headers=HEADERS_BROWSER, timeout=15, verify=False)
                res_web.raise_for_status()
                
                emails_trovate = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res_web.text)
                
                esclusioni_file = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css', 'sentry.io')
                esclusioni_pec = [
                    'pec@', '@pec', '.pec.', 'legalmail', 'postacert', 'certificata', 
                    'sicurezzapostale', 'telecompost', '@cert.', 'pcert.it', 'arubapec',
                    'nome@', 'esempio@', 'example@', 'test@', 'tuamail@', 'tuaemail@',
                    '@azienda.it', '@dominio.it', '@email.it', '@esempio.it', '@example.com', '@domain.com'
                ]
                
                emails_pulite = list(set([
                    e.lower() for e in emails_trovate 
                    if not e.lower().endswith(esclusioni_file)
                    and not any(pec in e.lower() for pec in esclusioni_pec)
                ]))
                
                email_suggerita = emails_pulite[0] if emails_pulite else "NESSUNA"

                soup = BeautifulSoup(res_web.text, 'html.parser')
                titolo = soup.title.string.strip() if soup.title and soup.title.string else "Sito Aziendale"
                testo = soup.get_text(separator=' ', strip=True)[:10000]
                
                prompt_web = f"""
                Analizza questo testo di una pagina web per una società di ricerca e selezione agenti di commercio.
                URL della pagina: {url_sito}
                Titolo pagina: {titolo}
                
                Estrai 7 informazioni chiave in modo sintetico:
                
                1. ESITO: Classifica in "AGENTE", "DIPENDENTE" oppure "ESCLUSO".
                REGOLA TASSATIVA PER "AGENTE":
                Scrivi "AGENTE" SOLO ED ESCLUSIVAMENTE se nella pagina è presente un annuncio, una sezione "Lavora con noi / Collabora con noi" o un invito ESPLICITO a candidarsi / inviare il CV per diventare Agente di Commercio, Rappresentante, Venditore a P.IVA o Procacciatore.
                
                REGOLE DI ESCLUSIONE - Scrivi TASSATIVAMENTE "ESCLUSO" se rientra in uno di questi casi:
                - La pagina è una normale Homepage, pagina "Chi siamo", pagina "Prodotti/Servizi" o "Contatti" in cui NON c'è alcuna ricerca aperta di agenti o venditori.
                - La pagina "Rete vendita / Punti vendita / Distributori" serve solo ai clienti finali per trovare il rivenditore o l'agente di zona, ma NON contiene un annuncio di ricerca di nuovi agenti.
                - Multinazionali estere, colossi industriali globali o società quotate in borsa (cerchiamo solo PMI e aziende italiane snelle).
                - Vendita diretta a domicilio / incaricati alle vendite / network marketing (es. Just, Folletto, Avon, Herbalife).
                - Portali di annunci generici, directory di aziende (es. Atoka, Empresite), blog di notizie o agenzie interinali.
                - Agenzie immobiliari, assicurative, finanziarie, noleggio auto/NCC, scuole di recupero anni scolastici o tour operator/viaggi.
                - Aziende contratti Luce, Gas, Energia, Telefonia.
                - Concessionarie auto o automotive.
                - Agenzie/studi consulenza per agenti o software CRM per agenti.
                - Verisure o venditoriadistanza.it.
                
                2. NOME_AZIENDA: VERO nome del brand/azienda mandante. (Se ESCLUSO scrivi SCONOSCIUTO).
                3. EMAIL: Indirizzo email di contatto REALE (NON inserire mai email finte di esempio come nome@azienda.it né indirizzi PEC come @pcert.it o @legalmail.it. Nota: ho estratto questa email dal codice sorgente: {email_suggerita}. Usala se valida, altrimenti cercala nel testo. Se assente scrivi NESSUNA).
                4. SETTORE: Breve specifica del settore nel quale opera l'azienda. Se non chiaro scrivi "--".
                5. TELEFONO: Numero di telefono principale. Escludi numeri di FAX o numeri di assistenza tecnica. Se non lo trovi scrivi "--".
                6. CITTA: La città della sede. Se non è un capoluogo di provincia, aggiungi la sigla della provincia (es. "BUSTO ARSIZIO VA"). Se non la trovi scrivi "--".
                7. REGIONE: Lo Stato/Regione (es. Lombardia, Piemonte). Se non la trovi scrivi "--".
                
                Rispondi ESATTAMENTE su una sola riga usando il separatore | tra i campi.
                Formato richiesto: ESITO | NOME_AZIENDA | EMAIL | SETTORE | TELEFONO | CITTA | REGIONE
                
                Testo: {testo}
                """
                
                time.sleep(20)
                max_tentativi = 3
                for t in range(max_tentativi):
                    try:
                        risposta = client.models.generate_content(model='gemini-3.6-flash', contents=prompt_web)
                        
                        parti = risposta.text.strip().replace("*", "").split('|')
                        
                        esito = parti[0].strip().upper() if len(parti) > 0 else "SCONOSCIUTO"
                        nome_reale = parti[1].strip() if len(parti) > 1 else "SCONOSCIUTO"
                        email = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
                        if not email_valida(email):
                            email = "NESSUNA"
                        settore = parti[3].strip() if len(parti) > 3 else "--"
                        
                        telefono_sito = parti[4].strip() if len(parti) > 4 else "--"
                        citta_sito = parti[5].strip() if len(parti) > 5 else "--"
                        regione_sito = parti[6].strip() if len(parti) > 6 else "--"
                        
                        break 
                    except Exception as e_ia:
                        if t < max_tentativi - 1: time.sleep(30)
                        else: raise e_ia
                
                if "AGENTE" not in esito:
                    worksheet_master.update(values=[[dominio, titolo, esito, data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                else:
                    worksheet_master.update(values=[[titolo, esito, data_odierna]], range_name=f"C{numero_riga}:E{numero_riga}")
                time.sleep(1.5) 
                
                if "AGENTE" in esito:
                    nome_pulito = pulisci_nome_azienda(nome_reale)
                    
                    if (nome_pulito and nome_pulito in aziende_gia_in_prospect) or (dominio in domini_gia_in_prospect):
                        print(f"Salto inserimento {nome_reale}: già presente in Nuovi Prospect.")
                        continue

                    nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_reale, dominio, email)
                    
                    tel_google, ind_google = cerca_dati_aziendali_osint(nome_reale)
                    
                    telefono_finale = tel_google if tel_google else telefono_sito
                    
                    citta_finale = citta_sito
                    regione_finale = regione_sito
                    if ind_google:
                        citta_g, reg_g = formatta_indirizzo_osint(ind_google)
                        if citta_g != "--": citta_finale = citta_g
                        if reg_g != "--": regione_finale = reg_g
                    
                    # Controlla se il contatto esiste già su HubSpot: se esiste, aggiunge i nuovi dati senza cancellare i vecchi
                    contact_id_esistente = cerca_id_hubspot_contact(dominio, nome_reale)
                    if contact_id_esistente:
                        stato_crm = arricchisci_contatto_hubspot_esistente(
                            contact_id_esistente,
                            url_sito=url_sito,
                            email_generica=email,
                            nome_dm=nome_dm,
                            ruolo_dm=ruolo_dm,
                            email_dm=email_dm,
                            settore=settore,
                            telefono=telefono_finale,
                            citta=citta_finale,
                            regione=regione_finale
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
                        nome_reale.upper(),
                        url_sito,
                        titolo,
                        esito,
                        stato_crm,
                        email_azienda_finale,
                        referente_completo,
                        email_referente_finale,
                        data_odierna
                    ]
                    worksheet_assistente.append_row(nuova_riga)
                    
                    if nome_pulito:
                        aziende_gia_in_prospect.add(nome_pulito)
                    domini_gia_in_prospect.add(dominio)
                
            except Exception as e:
                worksheet_master.update(values=[[dominio, "Sito non raggiungibile", "ERRORE", data_odierna]], range_name=f"B{numero_riga}:E{numero_riga}")
                time.sleep(1.5)

if __name__ == "__main__":
    main()
