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

# --- 2. MATRICE DI RICERCA ---
keywords = ['"ricerca agenti di commercio"', '"lavora con noi" "agente di commercio"', '"posizioni aperte" "procacciatore"']
settori = ["Edilizia", "Meccanica", "Software", "Medicale", "Ho.Re.Ca", "Alimentare", "Termoidraulica", "Cosmesi", "Forniture industriali"]
province = ["Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", "Treviso", "Bergamo", "Firenze", "Napoli"]
esclusioni = "-site:indeed.com -site:infojobs.it -site:linkedin.com -site:subito.it -site:cercoagente.it -site:venditori.it"

def main():
    ddgs = DDGS()
    
    # Eseguiamo 3 query alla volta per raccogliere prospect (circa 30 url)
    for _ in range(3):
        query = f'{random.choice(keywords)} {random.choice(settori)} {random.choice(province)} {esclusioni}'
        print(f"Cerco: {query}")
        
        try:
            # Ricerca su DuckDuckGo
            risultati = list(ddgs.text(query, max_results=10))
            
            if not risultati:
                print("Nessun risultato trovato per questa query.")
                time.sleep(3)
                continue
                
            # Trova la prima riga vuota nella colonna B (URL)
            colonna_b = worksheet.col_values(2)
            prima_riga_vuota = len(colonna_b) + 1
            
            dati_da_inserire = []
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link = item.get('href', '')
                
                # Salviamo solo link a pagine web (evitiamo file pdf o strani formati)
                if link and not link.endswith('.pdf'):
                    dati_da_inserire.append([titolo, link])
            
            if dati_da_inserire:
                # Inserisce i risultati nel foglio (Colonna A e B)
                intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
                worksheet.update(values=dati_da_inserire, range_name=intervallo)
                print(f"Aggiunti {len(dati_da_inserire)} nuovi prospect nel foglio!")
                
        except Exception as e:
            print(f"Errore durante la ricerca: {e}")
            
        # Pausa per non farci bloccare dal motore di ricerca
        time.sleep(4)

if __name__ == "__main__":
    main()
