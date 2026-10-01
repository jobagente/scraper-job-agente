import os
import json
import random
import time
import gspread
from google.oauth2.service_account import Credentials
from duckduckgo_search import DDGS

# --- 1. CONNESSIONE GOOGLE SHEETS ---
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("ERRORE: Variabile GCP_CREDENTIALS non trovata.")

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

# --- 2. MATRICE DI RICERCA OTTIMIZZATA ---
keywords = ['"ricerca agenti di commercio"', 'lavora con noi agente', 'posizioni aperte commerciale', 'ricerca procacciatori']
province = ["Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", "Treviso", "Bergamo", "Firenze", "Napoli"]

# Facciamo il filtro dei siti direttamente in Python (molto più preciso e non confonde il motore di ricerca)
siti_da_escludere = [
    'indeed.com', 'infojobs.it', 'linkedin.com', 'subito.it', 
    'cercoagente.it', 'venditori.it', 'bakeca.it', 'glassdoor.it', 
    'jooble.org', 'monster.it', 'wikihow.com', 'wikipedia.org'
]

def main():
    ddgs = DDGS()
    
    for _ in range(3):
        # Query pulita: solo parola chiave e provincia (niente operatori complessi)
        query = f'{random.choice(keywords)} {random.choice(province)}'
        print(f"Cerco: {query}")
        
        try:
            # region='it-it' FORZA DuckDuckGo a restituire risultati italiani e pertinenti
            risultati = list(ddgs.text(query, region='it-it', max_results=15))
            
            if not risultati:
                print("Nessun risultato trovato per questa query.")
                time.sleep(3)
                continue
                
            colonna_b = worksheet.col_values(2)
            prima_riga_vuota = len(colonna_b) + 1
            
            dati_da_inserire = []
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link = item.get('href', '')
                
                # Filtri: scarta PDF e scarta i siti presenti nella lista delle esclusioni
                if link and not link.endswith('.pdf'):
                    # any() verifica se c'è almeno un "sito_vietato" all'interno del "link"
                    if not any(sito_vietato in link for sito_vietato in siti_da_escludere):
                        dati_da_inserire.append([titolo, link])
            
            if dati_da_inserire:
                intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
                worksheet.update(values=dati_da_inserire, range_name=intervallo)
                print(f"Aggiunti {len(dati_da_inserire)} prospect nel foglio!")
                
        except Exception as e:
            print(f"Errore durante la ricerca: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    main()
