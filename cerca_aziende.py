import os
import json
import random
import time
import requests
import gspread
from urllib.parse import urlparse
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

# Keywords B2B pure con operatori di esclusione (-) per respingere il retail
keywords = [
    'lavora con noi agente enasarco -negozio -retail',
    'posizioni aperte procacciatore b2b -commesso -supermercato',
    'ricerca agenti plurimandatari -franchising -promoter',
    'candidatura commerciale partita iva -store -GDO',
    'invia curriculum consulente commerciale b2b'
]

# Ampliamento massiccio del bacino geografico
province = [
    "Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", 
    "Treviso", "Bergamo", "Firenze", "Napoli", "Varese", "Monza", "Como", "Modena", 
    "Parma", "Reggio Emilia", "Cuneo", "Udine", "Pordenone"
]

# Blacklist aggiornata con i nuovi portali e siti retail/social
siti_da_escludere = [
    'indeed', 'infojobs', 'linkedin', 'subito', 'cercoagente', 'venditori', 
    'bakeca', 'glassdoor', 'jooble', 'monster', 'wikihow', 'wikipedia', 'youtube',
    'lavoro.it', 'jobeka', 'applavoro', 'jobsora', 'rappresentanti', 'startup.jobs', 
    'jobijoba', 'trabajo', 'gigroup', 'randstad', 'grafton', 'adecco', 'manpower', 
    'generazionevincente', 'trovolavoro', 'corriere', 'annunci', 'bancalavoro', 
    'jobgratis', 'cornerjob', 'aliagenzia', 'synergie', 'pagepersonnel', 
    'michaelpage', 'hays', 'quojobis', 'orienta', 'maw.it', 'inhrgroup', 'careerjet',
    'impiego24', 'lavorofacile', 'ialweb', 'bachecalavoro', 'jobrapido', 'cercolavoro',
    'simplyhired', 'altamiraweb', 'inrecruiting', 'niuma', 'cving', 'talent', 'metis',
    'agentscout', 'jobleads', 'whatjobs', 'cercoagenti', 'federagenti', 'camcom', 'ascom',
    'kijiji', 'mitula', 'neuvoo', 'adzuna', 'trovit', 'tuolavoro', 'fashionjobs', 
    'risorse.it', 'lifein', 'instagram', 'facebook', 'tiktok', 'bancaclv'
]

def main():
    # Aumentati i cicli a 25 per massimizzare il volume notturno
    for _ in range(25):
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
            domini_inseriti = set() 
            
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link = item.get('link', '').lower()
                
                if link and not link.endswith('.pdf'):
                    dominio_estratto = urlparse(link).netloc.replace('www.', '')
                    
                    if not any(sito_vietato in link for sito_vietato in siti_da_escludere):
                        if dominio_estratto not in domini_inseriti and not any(link == riga[1] for riga in dati_da_inserire):
                            dati_da_inserire.append([titolo, item.get('link', '')])
                            domini_inseriti.add(dominio_estratto) 
                
                # Consente fino a 40 estrazioni per singola query valida
                if len(dati_da_inserire) >= 40:
                    break
            
            if dati_da_inserire:
                intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
                worksheet.update(values=dati_da_inserire, range_name=intervallo)
                print(f"Aggiunti {len(dati_da_inserire)} prospect mandanti!")
                
        except requests.exceptions.HTTPError as err:
            print(f"Errore HTTP da Serper: {err}")
        except Exception as e:
            print(f"Errore ricerca: {e}")
            
        # Pausa allungata per evitare blocchi con 25 cicli
        time.sleep(3)

if __name__ == "__main__":
    main()
