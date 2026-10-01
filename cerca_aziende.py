import os
import json
import random
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONI ---
creds_json = os.environ.get('GCP_CREDENTIALS')
serper_api_key = os.environ.get('SERPER_API_KEY')

if not creds_json or not serper_api_key:
    raise ValueError("ERRORE: Variabili mancanti (GCP_CREDENTIALS o SERPER_API_KEY).")

# --- 2. CONNESSIONE GOOGLE SHEETS ---
creds_dict = json.loads(creds_json)
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0"

try:
    sh = gc.open_by_url(URL_FOGLIO)
    worksheet = sh.sheet1
except Exception as e:
    print(f"Errore di connessione al foglio: {e}")
    exit()

# --- 3. MATRICE DI RICERCA ---
keywords = ['"ricerca agenti di commercio"', 'lavora con noi agente', 'posizioni aperte commerciale', 'ricerca procacciatori']
province = ["Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", "Treviso", "Bergamo", "Firenze", "Napoli"]
siti_da_escludere = [
    'indeed.com', 'infojobs.it', 'linkedin.com', 'subito.it', 
    'cercoagente.it', 'venditori.it', 'bakeca.it', 'glassdoor.it', 
    'jooble.org', 'monster.it', 'wikihow.com', 'wikipedia.org', 'youtube.com'
]

def main():
    for _ in range(3):
        query = f'{random.choice(keywords)} {random.choice(province)}'
        print(f"Cerco sul VERO Google (via Serper): {query}")
        
        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "gl": "it",  # Geolocalizza in Italia
            "hl": "it",  # Cerca in Italiano
            "num": 10
        })
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            response.raise_for_status()
            data = response.json()
            
            risultati = data.get('organic', [])
            if not risultati:
                print("Nessun risultato per questa query.")
                continue
                
            colonna_b = worksheet.col_values(2)
            prima_riga_vuota = len(colonna_b) + 1
            
            dati_da_inserire = []
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link = item.get('link', '')
                
                # Salviamo il link se non è un PDF e non è un portale di annunci
                if link and not link.endswith('.pdf'):
                    if not any(sito_vietato in link for sito_vietato in siti_da_escludere):
                        dati_da_inserire.append([titolo, link])
            
            if dati_da_inserire:
                intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
                worksheet.update(values=dati_da_inserire, range_name=intervallo)
                print(f"Aggiunti {len(dati_da_inserire)} prospect di alta qualità!")
                
        except Exception as e:
            print(f"Errore durante la ricerca API: {e}")
            
        time.sleep(2)

if __name__ == "__main__":
    main()
