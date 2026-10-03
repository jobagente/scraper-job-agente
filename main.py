import os
import json
import time
import gspread
import requests
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.service_account import Credentials

creds_json = os.environ.get('GCP_CREDENTIALS')
gemini_api_key = os.environ.get('GEMINI_API_KEY')

creds_dict = json.loads(creds_json)
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
client = genai.Client(api_key=gemini_api_key)

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet_master = sh.sheet1
        
        # Connessione al foglio dell'assistente
        try:
            worksheet_assistente = sh.worksheet("Nuovi Prospect")
        except gspread.exceptions.WorksheetNotFound:
            print("ERRORE: Crea un nuovo foglio in basso a sinistra chiamato 'Nuovi Prospect'")
            return
            
    except Exception as e:
        print(f"Errore di connessione: {e}")
        return

    dati = worksheet_master.get_all_values()
    
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2: continue
            
        nome_azienda = riga[0].strip()
        url = riga[1].strip()
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        if url and (not esito_attuale or "ERRORE" in esito_attuale):
            numero_riga_foglio = i + 1
            print(f"Processo riga {numero_riga_foglio}: {url}")
            
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                risposta_web = requests.get(url, headers=headers, timeout=15)
                risposta_web.raise_for_status()
                
                soup = BeautifulSoup(risposta_web.text, 'html.parser')
                titolo_pagina = soup.title.string.strip() if soup.title and soup.title.string else "Sito Aziendale"
                testo_pagina = soup.get_text(separator=' ', strip=True)[:10000]
                
                prompt = f"""
                Agisci come un selezionatore esperto. Analizza il seguente testo estratto da un annuncio di lavoro o pagina 'Lavora con noi'.
                Stabilisci se la posizione offerta è per un "Agente" (partita IVA, procacciatore, venditore indipendente) oppure per un "Dipendente" (assunzione diretta, contratto subordinato, impiegato).
                Rispondi SOLO ed ESCLUSIVAMENTE con una di queste due parole: AGENTE oppure DIPENDENTE. Non aggiungere altro.
                Testo: {testo_pagina}
                """
                
                time.sleep(20)
                
                max_tentativi = 3
                for tentativo in range(max_tentativi):
                    try:
                        risposta_ia = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
                        esito = risposta_ia.text.strip().upper().replace("*", "").replace(".", "")
                        break 
                    except Exception as error_ia:
                        print(f"Tentativo {tentativo + 1} fallito: {error_ia}")
                        if tentativo < max_tentativi - 1:
                            time.sleep(30)
                        else:
                            raise error_ia
                
                # Scrive i risultati nel Database Storico (Foglio 1)
                worksheet_master.update_cell(numero_riga_foglio, 3, titolo_pagina)
                worksheet_master.update_cell(numero_riga_foglio, 4, esito)
                
                # Se il prospect è valido, lo copia automaticamente nell'Inbox dell'Assistente
                if "AGENTE" in esito:
                    worksheet_assistente.append_row([nome_azienda, url, titolo_pagina, esito])
                    print(f"+++ Azienda {nome_azienda} copiata in Nuovi Prospect! +++")
                
            except requests.exceptions.RequestException:
                worksheet_master.update_cell(numero_riga_foglio, 4, "ERRORE: Sito non raggiungibile")
            except Exception as e:
                worksheet_master.update_cell(numero_riga_foglio, 4, f"ERRORE IA: {str(e)[:50]}")

if __name__ == "__main__":
    main()
