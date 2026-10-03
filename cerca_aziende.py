import os
import json
import random
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

creds_json = os.environ.get('GCP_CREDENTIALS')
serper_api_key = os.environ.get('SERPER_API_KEY')

if not creds_json or not serper_api_key:
    raise ValueError("ERRORE: Variabili mancanti (GCP_CREDENTIALS o SERPER_API_KEY).")

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

# Parole chiave in "plain text" senza virgolette o operatori per aggirare il blocco del piano gratuito
keywords = [
    'lavora con noi agente di commercio',
    'posizioni aperte rete vendita',
    'ricerca agenti candidatura',
    'invia curriculum procacciatore'
]
province = ["Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", "Treviso", "Bergamo", "Firenze", "Napoli"]

siti_da_escludere = [
    'indeed', 'infojobs', 'linkedin', 'subito', 'cercoagente', 'venditori', 
    'bakeca', 'glassdoor', 'jooble', 'monster', 'wikihow', 'wikipedia', 'youtube',
    'lavoro.it', 'jobeka', 'applavoro', 'jobsora', 'rappresentanti', 'startup.jobs', 
    'jobijoba', 'trabajo', 'gigroup', 'randstad', 'grafton', 'adecco', 'manpower', 
    'generazionevincente', 'trovolavoro', 'corriere', 'annunci', 'bancalavoro', 
    'jobgratis', 'cornerjob', 'aliagenzia', 'synergie', 'pagepersonnel', 
    'michaelpage', 'hays', 'quojobis', 'orienta', 'maw.it', 'inhrgroup', 'careerjet',
    'impiego24', 'lavorofacile', 'ialweb', 'bachecalavoro', 'jobrapido', 'cercolavoro'
]

def main():
    for _ in range(3):
        query = f'{random.choice(keywords)} {random.choice(province)}'
        print(f"Eseguo query mirata: {query}")
        
        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "gl": "it",
            "hl": "it",
            "num": 100
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
                print("Nessun risultato utile.")
                continue
                
            colonna_b = worksheet.col_values(2)
            prima_riga_vuota = len(colonna_b) + 1
            
            dati_da_inserire = []
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link = item.get('link', '').lower()
                
                if link and not link.endswith('.pdf'):
                    if not any(sito_vietato in link for sito_vietato in siti_da_escludere):
                        if not any(link == riga[1] for riga in dati_da_inserire):
                            dati_da_inserire.append([titolo, item.get('link', '')])
                
                if len(dati_da_inserire) >= 20:
                    break
            
            if dati_da_inserire:
                intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
                worksheet.update(values=dati_da_inserire, range_name=intervallo)
                print(f"Aggiunti {len(dati_da_inserire)} prospect mandanti!")
                
        except requests.exceptions.HTTPError as err:
            print(f"Errore HTTP da Serper: {err}")
            print(f"Dettaglio risposta: {err.response.text}")
        except Exception as e:
            print(f"Errore ricerca: {e}")
            
        time.sleep(2)

if __name__ == "__main__":
    main()
