import os
import json
import time
import requests
import gspread
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse
from datetime import datetime  # NUOVO MODULO PER LA DATA

creds_json = os.environ.get('GCP_CREDENTIALS')
gemini_api_key = os.environ.get('GEMINI_API_KEY')
hubspot_token = os.environ.get('HUBSPOT_ACCESS_TOKEN')

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
    except:
        pass
    return False

def crea_hubspot_contact(nome_reale, url_sito, email):
    if not hubspot_token: return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    nome_maiuscolo = nome_reale.upper()
    
    properties = {
        "firstname": nome_maiuscolo,
        "website": url_sito,
        "company": nome_maiuscolo,
        "hubspot_owner_id": "13315750",
        "note_appartenenza": "PROSPECT WEB"
    }
    
    if email and "@" in email and email.lower() != "nessuna":
        properties["email"] = email
        
    try:
        url_cont = "https://api.hubapi.com/crm/v3/objects/contacts"
        res = requests.post(url_cont, headers=headers, json={"properties": properties})
        if res.status_code in (200, 201):
            return "Inserito in HubSpot"
        else:
            errore = res.json().get("message", "Errore sconosciuto")
            print(f"HubSpot ha rifiutato {nome_maiuscolo}: {errore}")
            return f"Errore CRM: {errore}"
    except Exception as e:
        return f"Errore di connessione CRM"

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet_master = sh.sheet1
        worksheet_assistente = sh.worksheet("Nuovi Prospect")
    except Exception as e:
        print(f"Errore foglio: {e}")
        return

    dati = worksheet_master.get_all_values()
    
    # Prepara la data odierna nel formato Giorno/Mese/Anno
    data_odierna = datetime.now().strftime('%d/%m/%Y')
    
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
                
                prompt = f"""
                Analizza questo testo di una pagina web per una società di ricerca agenti.
                Devi estrarre 3 informazioni chiave in modo sintetico:
                
                1. ESITO: Classifica in "AGENTE" (se cercano P.IVA e sono mandanti validi) o "DIPENDENTE".
                ATTENZIONE - REGOLE DI ESCLUSIONE: Se il testo rientra in una di queste categorie, scrivi TASSATIVAMENTE "ESCLUSO":
                - Portali di annunci generici (es. JobSavior, TuoAgente, Bakeca, Indeed) o agenzie interinali.
                - Agenzie immobiliari (qualsiasi tipo).
                - Aziende che propongono contratti di Luce, Gas ed Energia.
                - Concessionarie di auto o automotive.
                - Agenzie o studi di consulenza (es. Studio Stella Associati) che offrono servizi/consulenza *agli* agenti di commercio invece di assumerli.
                - Le aziende specifiche: "Verisure" e "venditoriadistanza.it".
                
                2. NOME_AZIENDA: Estrai il VERO nome del brand/azienda mandante (es. Perfetti Van Melle). Non inserire MAI la posizione lavorativa o la città. Se l'esito è ESCLUSO, scrivi SCONOSCIUTO.
                3. EMAIL: Trova un indirizzo email di contatto. Se assente, scrivi NESSUNA.
                
                Rispondi ESATTAMENTE su una sola riga in questo formato: ESITO | NOME_AZIENDA | EMAIL
                
                Esempio 1: AGENTE | Perfetti Van Melle | hr@azienda.it
                Esempio 2: ESCLUSO | SCONOSCIUTO | NESSUNA
                Esempio 3: DIPENDENTE | Esselunga | NESSUNA
                
                Testo: {testo}
                """
                
                time.sleep(20)
                
                max_tentativi = 3
                for t in range(max_tentativi):
                    try:
                        risposta = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
                        risultato_raw = risposta.text.strip().replace("*", "")
                        parti = risultato_raw.split('|')
                        
                        esito = parti[0].strip().upper()
                        nome_reale = parti[1].strip() if len(parti) > 1 else "SCONOSCIUTO"
                        email = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
                        break 
                    except Exception as e_ia:
                        if t < max_tentativi - 1: time.sleep(30)
                        else: raise e_ia
                
                worksheet_master.update_cell(numero_riga, 3, titolo)
                worksheet_master.update_cell(numero_riga, 4, esito)
                worksheet_master.update_cell(numero_riga, 5, data_odierna) # SCRIVE LA DATA NELLA COLONNA E
                
                if "AGENTE" in esito:
                    dominio = urlparse(url_sito).netloc.replace('www.', '')
                    esiste_in_crm = check_hubspot_contact(dominio, nome_reale)
                    
                    if esiste_in_crm:
                        stato_crm = "Già in HubSpot"
                    else:
                        stato_crm = crea_hubspot_contact(nome_reale, url_sito, email)
                        
                    # AGGIUNGE LA DATA COME 7ª COLONNA (COLONNA G)
                    worksheet_assistente.append_row([nome_reale.upper(), url_sito, titolo, esito, stato_crm, email, data_odierna])
                
            except Exception as e:
                worksheet_master.update_cell(numero_riga, 4, f"ERRORE IA: {str(e)[:50]}")
                worksheet_master.update_cell(numero_riga, 5, data_odierna) # SCRIVE LA DATA ANCHE IN CASO DI ERRORE

if __name__ == "__main__":
    main()
