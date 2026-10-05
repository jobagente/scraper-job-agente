import os
import json
import time
import requests
import gspread
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse

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
    
    # Cerca nei Contatti per dominio web OPPURE per nome azienda per evitare duplicati
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "firstname", "operator": "EQ", "value": nome_azienda}]},
            {"filters": [{"propertyName": "company", "operator": "EQ", "value": nome_azienda}]}
        ]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get('total', 0) > 0
    except:
        pass
    return False

def crea_hubspot_contact(nome, url_sito, email):
    if not hubspot_token: return
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    # Compila la scheda Contatto come fai tu manualmente
    properties = {
        "firstname": nome,
        "website": url_sito,
        "company": nome
    }
    
    if email and "@" in email and email.lower() != "nessuna":
        properties["email"] = email
        
    try:
        url_cont = "https://api.hubapi.com/crm/v3/objects/contacts"
        requests.post(url_cont, headers=headers, json={"properties": properties})
    except:
        pass

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet_master = sh.sheet1
        worksheet_assistente = sh.worksheet("Nuovi Prospect")
    except Exception as e:
        print(f"Errore di connessione al foglio: {e}")
        return

    dati = worksheet_master.get_all_values()
    
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2: continue
            
        nome_azienda = riga[0].strip()
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
                Agisci come un selezionatore. Analizza questo testo di un annuncio.
                1. Classifica la posizione in "AGENTE" (partita IVA) o "DIPENDENTE".
                2. Trova un indirizzo email per contatti o candidature. Se assente, scrivi NESSUNA.
                
                Rispondi ESATTAMENTE su una sola riga usando questo formato: ESITO | EMAIL
                Esempio 1: AGENTE | hr@azienda.it
                Esempio 2: DIPENDENTE | NESSUNA
                
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
                        email = parti[1].strip().lower() if len(parti) > 1 else "NESSUNA"
                        break 
                    except Exception as e_ia:
                        print(f"Tentativo {t + 1} fallito: {e_ia}")
                        if t < max_tentativi - 1: time.sleep(30)
                        else: raise e_ia
                
                worksheet_master.update_cell(numero_riga, 3, titolo)
                worksheet_master.update_cell(numero_riga, 4, esito)
                
                if "AGENTE" in esito:
                    dominio = urlparse(url_sito).netloc.replace('www.', '')
                    
                    # Usa la nuova funzione dedicata ai Contatti
                    esiste_in_crm = check_hubspot_contact(dominio, nome_azienda)
                    
                    if esiste_in_crm:
                        stato_crm = "Presente in HubSpot"
                        print(f"Contatto {nome_azienda} già in HubSpot. Salto la creazione.")
                    else:
                        stato_crm = "Inserito in HubSpot"
                        # Crea il record nei Contatti
                        crea_hubspot_contact(nome_azienda, url_sito, email)
                        print(f"Contatto {nome_azienda} creato in HubSpot con email: {email}")
                        
                    worksheet_assistente.append_row([nome_azienda, url_sito, titolo, esito, stato_crm, email])
                
            except requests.exceptions.RequestException:
                worksheet_master.update_cell(numero_riga, 4, "ERRORE: Sito non raggiungibile")
            except Exception as e:
                worksheet_master.update_cell(numero_riga, 4, f"ERRORE IA: {str(e)[:50]}")

if __name__ == "__main__":
    main()
