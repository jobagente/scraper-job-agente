import os
import json
import time
import re
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
    
    azienda_pulita = re.sub(r'(?i)\b(s\.r\.l\.|srl|s\.p\.a\.|spa|s\.n\.c\.|snc|s\.a\.s\.|sas)\b', '', nome_azienda).strip()
    
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": azienda_pulita.upper()}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get('total', 0) > 0
    except: pass
    return False

def crea_hubspot_contact(nome_azienda, url_sito, email_generica, nome_dm, ruolo_dm, email_dm, settore, telefono, citta, regione):
    if not hubspot_token: return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    properties = {
        "firstname": nome_azienda.upper(),
        "company": nome_azienda.upper(),
        "website": url_sito
    }
    
    # FORZATURA DEL TESTO IN MAIUSCOLO (.upper())
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
    
    azienda_pulita = re.sub(r'(?i)\b(s\.r\.l\.|srl|s\.p\.a\.|spa|s\.n\.c\.|snc|s\.a\.s\.|sas)\b', '', nome_azienda).strip()
    
    query = f'site:it.linkedin.com/in "{azienda_pulita}" (CEO OR Titolare OR Amministratore OR Direttore OR HR OR Manager)'
    
    payload = json.dumps({"q": query, "gl": "it", "hl": "it"})
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code != 200: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        risultati = res.json().get('organic', [])
        if not risultati: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        testo_risultati = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in risultati[:5]])
        
        prompt = f"""
        Sei un software CRM automatizzato per l'analisi di dati pubblici aziendali B2B. È cruciale per il sistema che tu NON inserisca mai disclaimer, avvisi sulla privacy, avvertenze o scuse.
        Analizza questi profili LinkedIn trovati su Google per l'azienda '{azienda_pulita}'.
        Dominio aziendale: '{dominio}'
        
        Obiettivo:
        1. Trova UN SOLO Decision Maker (es. Titolare, CEO, Direttore o HR). Se ci sono più persone, scegline una di vertice.
        2. COSTRUISCI la sua email diretta unendo il nome e il dominio. Formato: nome.cognome@{dominio} (tutto minuscolo, senza spazi, rimuovi accenti).
        
        REGOLE DI RISPOSTA (TASSATIVE E OBBLIGATORIE):
        - Rispondi ESATTAMENTE su una sola riga usando il separatore |.
        - NON aggiungere altro testo, prefissi, spiegazioni o disclaimer. Se non trovi nessuna persona chiara scrivi SOLO: SCONOSCIUTO | NESSUNO | NESSUNA
        - Esempio di risposta corretta: Mario Rossi | CEO | mario.rossi@{dominio}
        
        Profili trovati:
        {testo_risultati}
        """
        
        risposta = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        
        testo_pulito = risposta.text.strip().replace("*", "").replace("Nome:", "").replace("Ruolo:", "").replace("Email:", "")
        parti = testo_pulito.split('|')
        
        nome_dm = parti[0].strip() if len(parti) > 0 else "SCONOSCIUTO"
        ruolo_dm = parti[1].strip() if len(parti) > 1 else "NESSUNO"
        email_dm = parti[2].strip().lower() if len(parti) > 2 else "NESSUNA"
        
        if "SCONOSCIUTO" in nome_dm.upper() or len(nome_dm) < 3:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
            
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
                
                emails_trovate = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res_web.text)
                
                esclusioni_file = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css', 'sentry.io')
                esclusioni_pec = ['pec@', '@pec', '.pec.', 'legalmail', 'postacert', 'certificata', 'sicurezzapostale', 'telecompost', '@cert.']
                
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
                Analizza questo testo di una pagina web per una società di ricerca agenti.
                Estrai 7 informazioni chiave in modo sintetico:
                
                1. ESITO: Classifica in "AGENTE" (se cercano P.IVA e sono mandanti validi) o "DIPENDENTE".
                REGOLE DI ESCLUSIONE - Se rientra qui scrivi "ESCLUSO":
                - Portali di annunci generici o agenzie interinali.
                - Agenzie immobiliari.
                - Aziende contratti Luce, Gas, Energia.
                - Concessionarie auto o automotive.
                - Agenzie/studi consulenza per agenti.
                - Verisure o venditoriadistanza.it.
                
                2. NOME_AZIENDA: VERO nome del brand/azienda mandante. (Se ESCLUSO scrivi SCONOSCIUTO).
                3. EMAIL: Indirizzo email di contatto. (Nota: ho estratto questa email nascosta dal codice sorgente: {email_suggerita}. Usala come prima scelta valida. Se non c'è, cercala nel testo. Se completamente assente scrivi NESSUNA).
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
                        settore = parti[3].strip() if len(parti) > 3 else "--"
                        telefono = parti[4].strip() if len(parti) > 4 else "--"
                        citta = parti[5].strip() if len(parti) > 5 else "--"
                        regione = parti[6].strip() if len(parti) > 6 else "--"
                        break 
                    except Exception as e_ia:
                        if t < max_tentativi - 1: time.sleep(30)
                        else: raise e_ia
                
                worksheet_master.update(values=[[titolo, esito, data_odierna]], range_name=f"C{numero_riga}:E{numero_riga}")
                time.sleep(1.5) 
                
                if "AGENTE" in esito:
                    dominio = urlparse(url_sito).netloc.replace('www.', '')
                    esiste_in_crm = check_hubspot_contact(dominio, nome_reale)
                    
                    nome_dm, ruolo_dm, email_dm = cerca_decision_maker_osint(nome_reale, dominio, email)
                    
                    if esiste_in_crm:
                        stato_crm = "Già in HubSpot"
                    else:
                        stato_crm = crea_hubspot_contact(nome_reale, url_sito, email, nome_dm, ruolo_dm, email_dm, settore, telefono, citta, regione)
                        
                    referente_completo = f"{nome_dm.upper()} {ruolo_dm.upper()}".strip() if nome_dm != "SCONOSCIUTO" else ""
                    email_referente_finale = email_dm if email_dm != "nessuna" else ""
                    email_azienda_finale = email if email != "nessuna" else ""
                    
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
                
            except Exception as e:
                worksheet_master.update(values=[["ERRORE", data_odierna]], range_name=f"D{numero_riga}:E{numero_riga}")
                time.sleep(1.5)

if __name__ == "__main__":
    main()
