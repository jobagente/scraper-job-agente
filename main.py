import os
import json
import gspread
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
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

genai.configure(api_key=gemini_api_key)
# Utilizziamo il modello ufficiale e stabile
model = genai.GenerativeModel('gemini-1.5-flash')

def main():
    # LINK COMPLETO DEL TUO FOGLIO GOOGLE
    URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0" 
    
    try:
        sh = gc.open_by_url(URL_FOGLIO)
        worksheet = sh.sheet1
    except Exception as e:
        print(f"Errore di connessione al link: {e}")
        return

    # Legge tutti i valori del foglio
    dati = worksheet.get_all_values()
    
    # Salta l'intestazione (riga 1) e processa dalla riga 2 in poi
    for i in range(1, len(dati)):
        riga = dati[i]
        if len(riga) < 2:
            continue
            
        url = riga[1].strip() # Colonna B (indice 1)
        
        # Gestione colonne C e D nel caso la riga sia vuota
        esito_attuale = riga[3].strip() if len(riga) > 3 else ""

        # Procediamo solo se c'è un URL e la colonna dell'esito è vuota o contiene un errore precedente
        if url and (not esito_attuale or "ERRORE" in esito_attuale):
            numero_riga_foglio = i + 1
            print(f"Processo riga {numero_riga_foglio}: {url}")
            
            try:
                # Facciamo finta di essere un browser reale per non farci bloccare dai siti
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                risposta_web = requests.get(url, headers=headers, timeout=15)
                risposta_web.raise_for_status()
                
                soup = BeautifulSoup(risposta_web.text, 'html.parser')
                
                # Estrae il titolo per la colonna C
                titolo_pagina = soup.title.string.strip() if soup.title and soup.title.string else "Titolo non disponibile"
                
                # Estrae il testo (limitato a 10000 caratteri) per l'Intelligenza Artificiale
                testo_pagina = soup.get_text(separator=' ', strip=True)[:10000]
                
                # Prepara il comando per Gemini
                prompt = f"""
                Agisci come un selezionatore esperto. Analizza il seguente testo estratto da un annuncio di lavoro.
                Stabilisci se la posizione offerta è per un "Agente" (partita IVA, procacciatore, venditore indipendente) oppure per un "Dipendente" (assunzione diretta, contratto subordinato, impiegato).
                Rispondi SOLO ed ESCLUSIVAMENTE con una di queste due parole: AGENTE oppure DIPENDENTE. Non aggiungere altro.
                
                Testo:
                {testo_pagina}
                """
                
                # Interroga l'IA
                risposta_ia = model.generate_content(prompt)
                esito = risposta_ia.text.strip().upper().replace("*", "").replace(".", "")
                
                # Scrive i risultati sul foglio Excel
                worksheet.update_cell(numero_riga_foglio, 3, titolo_pagina) # Colonna C
                worksheet.update_cell(numero_riga_foglio, 4, esito)         # Colonna D
                print(f"Riga {numero_riga_foglio} completata: {esito}")
                
            except requests.exceptions.RequestException:
                worksheet.update_cell(numero_riga_foglio, 4, "ERRORE: Sito non raggiungibile")
            except Exception as e:
                worksheet.update_cell(numero_riga_foglio, 4, f"ERRORE IA: {str(e)[:50]}")

if __name__ == "__main__":
    main()
