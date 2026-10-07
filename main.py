import os
import json
import time
import requests
import gspread
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse
from datetime import datetime

creds_json = os.environ.get('GCP_CREDENTIALS')
gemini_api_key = os.environ.get('GEMINI_API_KEY')
hubspot_token = os.environ.get('HUBSPOT_ACCESS_TOKEN')
serper_api_key = os.environ.get('SERPER_API_KEY')

creds_dict = json.loads(creds_json)
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
client = genai.Client(api_key=gemini_api_key)

def check_hubspot_contact(dominio, nome_azienda):
    if not hubspot_token: return False
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    nome_maiuscolo = nome_azienda.upper()
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "company", "operator": "EQ", "value": nome_maiuscolo}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get('total', 0) > 0
    except: pass
    return False

def crea_hubspot_contact(nome_azienda, url_sito, email_generica, nome_dm, ruolo_dm, email_dm):
    if not hubspot_token: return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    properties = {
        "firstname": nome_azienda.upper(),
        "company": nome_azienda.upper(),
        "website": url_sito
    }
    
    # GESTIONE REFERENTE
    if nome_dm and nome_dm != "SCONOSCIUTO":
        ruolo = ruolo_dm.upper() if ruolo_dm != "NESSUNO" else ""
        properties["referente"] = f"{nome_dm.upper()} {ruolo}".strip()
        
    # GESTIONE EMAIL PRINCIPALE E AGGIUNTIVA
    email_primaria = email_dm if (email_dm and "@" in email_dm and email_dm != "nessuna") else email_generica
    email_secondaria = email_generica if (email_primaria == email_dm) else None

    if email_primaria and "@" in email_primaria and email_primaria != "nessuna":
        properties["email"] = email_primaria
        if email_secondaria and "@" in email_secondaria and email_secondaria != "nessuna" and email_secondaria != email_primaria:
            properties["hs_additional_emails"] = email_secondaria
        
    try:
        url_cont = "https://api.hubapi.com/crm/v3/objects/contacts"
        res = requests.post(url_cont, headers=headers, json={"properties": properties})
        if res.status_code in (200, 201):
            return "Inserito in HubSpot"
        else:
            errore = res.json().get("message", "Errore sconosciuto")
            return f"Errore CRM: {errore}"
    except Exception as e:
        return f"Errore CRM"

def cerca_decision_maker_osint(nome_azienda, dominio, email_generica):
    if not serper_api_key: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
    url = "https://google.serper.dev/search"
    
    # === NUOVA RICERCA POTENZIATA CON SINONIMI ===
    query = f'site:it.linkedin.com/in "{nome_azienda}" ("CEO" OR "Titolare" OR "Amministratore Delegato" OR "Direttore Generale" OR "Direttore Commerciale" OR "Direttore Vendite" OR "Responsabile Vendite" OR "Sales Manager" OR "Head of Sales" OR "Sales Director" OR "Risorse Umane" OR "HR" OR "Recruiter" OR "Talent Acquisition")'
    
    payload = json.dumps({"q": query, "gl": "it", "hl": "it"})
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code != 200: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        risultati = res.json().get('organic', [])
        if not risultati: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        testo_risultati = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in risultati[:5]])
        
        prompt = f"""
        Analizza questi profili LinkedIn.
        Azienda: '{nome_azienda}'
        Email info: '{email_generica}', Dominio: '{dominio}'
        
        Trova UN SOLO Decision Maker (es. Titolare, CEO, Direttore Commerciale o HR). Deduci l'email diretta.
        
        Rispondi ESATTAMENTE su una sola riga: NOME E COGNOME | RUOLO | EMAIL_DEDOTTA
        Se non trovi nessuno scrivi TASSATIVAMENTE: SCONOSCIUTO | NESSUNO | NESSUNA
        
        Profili:
        {testo_risultati}
        """
        
        risposta = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
        parti = risposta.text.strip().replace("*", "").split('|')
        
        nome_dm = parti[0].strip() if len(parti) > 0 else "SCONOSCIUTO"
        ruolo_dm = parti[1].strip() if len(parti) > 1 else "NESSUNO"
        email_dm = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
        return nome_dm, ruolo_dm, email_dm
    except Exception as e:
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet_master = sh.sheet1
        worksheet_assistente = sh.worksheet("Nuovi Prospect")
    except Exception as e: return

    dati = worksheet_master.get_all_values()
    data_odierna = datetime.now().strftime('%d/%m/%Y')
    
    # Prepara un dizionario per riga Nuovi Prospect da accodare (per evitare errori posizionali)
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2: continue
            
        url_sito = riga[1].strip()
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        if url_sito and (not esito_attuale or "ERRORE" in esito_attuale):
            numero_riga = i + 1
            print(f"Processo riga {numero_riga}: {url_sito}")
            
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res_web = requests.get(url_sito, headers=headers, timeout=15)
                res_web.raise_for_status()
                
                soup = BeautifulSoup(res_web.text, 'html.parser')
                titolo = soup.title.string.strip() if soup.title and soup.title.string else "Sito Aziendale"
                testo = soup.get_text(separator=' ', strip=True)[:10000]
                
                prompt_web = f"""
                Analizza questo testo di una pagina web per una società di ricerca agenti.
                Estrai 3 informazioni chiave in modo sintetico:
                
                1. ESITO: Classifica in "AGENTE" (se cercano P.IVA e sono mandanti validi) o "DIPENDENTE".
                REGOLE DI ESCLUSIONE - Se rientra qui scrivi "ESCLUSO":
                - Portali di annunci generici o agenzie interinali.
                - Agenzie immobiliari.
                - Aziende contratti Luce, Gas, Energia.
                - Concessionarie auto o automotive.
                - Agenzie/studi consulenza per agenti.
                - Verisure o venditoriadistanza.it.
                
                2. NOME_AZIENDA: VERO nome del brand/azienda mandante. (Se ESCLUSO scrivi SCONOSCIUTO).
                3. EMAIL: Indirizzo email di contatto. (Se assente scrivi NESSUNA).
                
                Rispondi su una sola riga: ESITO | NOME_AZIENDA | EMAIL
                
                Testo: {testo}
                """
                
                time.sleep(20)
                max_tentativi = 3
                for t in range(max_tentativi):
                    try:
                        risposta = client.models.generate_content(model='gemini-3.5-flash', contents=prompt_web)
                        parti = risposta.text.strip().replace("*", "").split('|')
                        
                        esito = parti[0].strip().upper()
                        nome_reale = parti[1].strip() if len(parti) > 1 else "SCONOSCIUTO"
                        email = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
                        break 
                    except Exception as e_ia:
                        if t < max_tentativi - 1: time.sleep(30)
                        else: raise e_ia
                
                worksheet_master.update_cell(numero_riga, 3, titolo)
                worksheet_master.update_cell(numero_riga, 4, esito)
                worksheet_master.update_cell(numero_riga, 5, data_odierna)
                
                if "AGENTE" in esito:
                    dominio = urlparse(url_sito).netloc.replace('www.', '')
                    esiste_in_crm = check_hubspot_contact(dominio, nome_reale)
                    
                    nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_reale, dominio, email)
                    
                    if esiste_in_crm:
                        stato_crm = "Già in HubSpot"
                    else:
                        stato_crm = crea_hubspot_contact(nome_reale, url_sito, email, nome_dm, ruolo_dm, email_dm)
                        
                    referente_completo = f"{nome_dm.upper()} {ruolo_dm.upper()}".strip() if nome_dm != "SCONOSCIUTO" else ""
                    email_referente_finale = email_dm if email_dm != "nessuna" else ""
                    email_azienda_finale = email if email != "nessuna" else ""
                    
                    # Usa una lista in un ordine bloccato per scrivere nel foglio "Nuovi Prospect"
                    nuova_riga = [
                        nome_reale.upper(),         # Colonna A
                        url_sito,                   # Colonna B
                        titolo,                     # Colonna C
                        esito,                      # Colonna D
                        stato_crm,                  # Colonna E
                        email_azienda_finale,       # Colonna F
                        referente_completo,         # Colonna G (Referente)
                        email_referente_finale,     # Colonna H (Email Referente)
                        data_odierna                # Colonna I (Data)
                    ]
                    worksheet_assistente.append_row(nuova_riga)
                
            except Exception as e:
                worksheet_master.update_cell(numero_riga, 4, f"ERRORE")
                worksheet_master.update_cell(numero_riga, 5, data_odierna)

if __name__ == "__main__":
    main()
