import os
import json
import time
import gspread
import requests
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE GOOGLE SHEETS ---
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("ERRORE: Variabile GCP_CREDENTIALS non trovata.")

creds_dict = json.loads(creds_json)
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

# --- 2. CONFIGURAZIONE GEMINI IA ---
gemini_api_key = os.environ.get('GEMINI_API_KEY')
if not gemini_api_key:
    raise ValueError("ERRORE: Variabile GEMINI_API_KEY non trovata.")

client = genai.Client(api_key=gemini_api_key)

def main():
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet = sh.sheet1
    except Exception as e:
        print(f"Errore di connessione al link: {e}")
        return

    dati = worksheet.get_all_values()
    
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2:
            continue
            
        url = riga[1].strip()
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        if url and (not esito_attuale or "ERRORE" in esito_attuale):
            numero_riga_foglio = i + 1
            print(f"Processo riga {numero_riga_foglio}: {url}")
            
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                risposta_web = requests.get(url, headers=headers, timeout=15)
                risposta_web.raise_for_status()
                
                soup = BeautifulSoup(risposta_web.text, 'html.parser')
                titolo_pagina = soup.title.string.strip() if soup.title and soup.title.string else "Titolo non disponibile"
                testo_pagina = soup.get_text(separator=' ', strip=True)[:10000]
                
                prompt = f"""
                Agisci come un selezionatore esperto. Analizza il seguente testo estratto da un annuncio di lavoro.
                Stabilisci se la posizione offerta è per un "Agente" (partita IVA, procacciatore, venditore indipendente) oppure per un "Dipendente" (assunzione diretta, contratto subordinato, impiegato).
                Rispondi SOLO ed ESCLUSIVAMENTE con una di queste due parole: AGENTE oppure DIPENDENTE. Non aggiungere altro.
                
                Testo:
                {testo_pagina}
                """
                
                time.sleep(3) # Pausa introdotta per prevenire l'errore 503
                
                risposta_ia = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=prompt
                )
                
                esito = risposta_ia.text.strip().upper().replace("*", "").replace(".", "")
                
                worksheet.update_cell(numero_riga_foglio, 3, titolo_pagina)
                worksheet.update_cell(numero_riga_foglio, 4, esito)
                print(f"Riga {numero_riga_foglio} completata: {esito}")
                
            except requests.exceptions.RequestException:
                worksheet.update_cell(numero_riga_foglio, 4, "ERRORE: Sito non raggiungibile")
            except Exception as e:
                worksheet.update_cell(numero_riga_foglio, 4, f"ERRORE IA: {str(e)[:50]}")

if __name__ == "__main__":
    main()
