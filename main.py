import os
import json
import time
import requests
import gspread
from bs4 import BeautifulSoup
import google.generativeai as genai

# Configurazione API e Credenziali dai Secret di GitHub
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
GCP_JSON = os.environ.get("GCP_CREDENTIALS")
SHEET_ID = "15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Connessione a Google Sheets
creds_dict = json.loads(GCP_JSON)
gc = gspread.service_account_from_dict(creds_dict)
sheet = gc.open_by_key(SHEET_ID).sheet1

def analizza_testo_con_ia(testo_pagina):
    if not testo_pagina or len(testo_pagina) < 50:
        return "ERRORE - Pagina vuota o non accessibile"
    
    prompt = f"""
    Agisci come un selezionatore esperto. Analizza questo testo estratto da una pagina 'Lavora con noi' aziendale.
    Il tuo obiettivo è identificare ESCLUSIVAMENTE se l'azienda sta cercando venditori indipendenti (Agenti di commercio, Agenti Enasarco, Procacciatori d'affari, mediatori con Partita IVA). 
    Ignora completamente le ricerche per dipendenti tradizionali, commessi o impiegati.
    
    Testo estratto:
    {testo_pagina[:6000]}
    
    Rispondi in modo secco:
    Scrivi "AGENTE" se cercano figure a P.IVA/Enasarco.
    Scrivi "DIPENDENTE/NESSUNO" se cercano altro o non ci sono posizioni commerciali aperte.
    Aggiungi un trattino "-" e una motivazione di massimo 15 parole.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace("\n", " ")
    except Exception as e:
        return f"ERRORE API IA: {str(e)}"

# Lettura dati dal foglio
dati = sheet.get_all_records()
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

for indice, riga in enumerate(dati):
    riga_foglio = indice + 2 
    url = riga.get("URL Pagina Lavora con noi", "").strip()
    esito_attuale = riga.get("Esito IA (Agente/Dipendente)", "").strip()
    
    # Processa solo le righe con un URL valido e non ancora analizzate
    if url and not esito_attuale:
        try:
            print(f"Scansione in corso: {url}")
            risposta_web = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(risposta_web.text, 'html.parser')
            testo_grezzo = soup.get_text(separator=' ', strip=True)
            
            esito_ia = analizza_testo_con_ia(testo_grezzo)
            
            # Aggiorna la cella dell'esito (Colonna D)
            sheet.update_cell(riga_foglio, 4, esito_ia)
            # Salva un'anteprima del testo per controllo (Colonna C)
            sheet.update_cell(riga_foglio, 3, testo_grezzo[:150] + "...")
            
            time.sleep(3) # Pausa di rispetto
            
        except Exception as e:
            sheet.update_cell(riga_foglio, 4, f"ERRORE SITO: {str(e)}")

print("Scansione completata.")
