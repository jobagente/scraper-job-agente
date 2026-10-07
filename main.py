import os
import json
import time
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
    nome_maiuscolo = nome_azienda.upper()
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "website", "operator": "CONTAINS_TOKEN", "value": dominio}]},
            {"filters": [{"propertyName": "company", "operator": "EQ", "value": nome_maiuscolo}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json().get('total', 0) > 0
    except: pass
    return False

def crea_hubspot_contact(nome_azienda, url_sito, email_generica, nome_dm, ruolo_dm, email_dm):
    if not hubspot_token: return "Token mancante"
    headers = {'Authorization': f'Bearer {hubspot_token}', 'Content-Type': 'application/json'}
    
    properties = {
        "firstname": nome_azienda.upper(),
        "company": nome_azienda.upper(),
        "website": url_sito
    }
    
    # GESTIONE REFERENTE
    if nome_dm and nome_dm != "SCONOSCIUTO":
        ruolo = ruolo_dm.upper() if ruolo_dm != "NESSUNO" else ""
        properties["referente"] = f"{nome_dm.upper()} {ruolo}".strip()
        
    # GESTIONE EMAIL PRINCIPALE E AGGIUNTIVA
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
    
    # === NUOVA RICERCA POTENZIATA CON SINONIMI ===
    query = f'site:it.linkedin.com/in "{nome_azienda}" ("CEO" OR "Titolare" OR "Amministratore Delegato" OR "Direttore Generale" OR "Direttore Commerciale" OR "Direttore Vendite" OR "Responsabile Vendite" OR "Sales Manager" OR "Head of Sales" OR "Sales Director" OR "Risorse Umane" OR "HR" OR "Recruiter" OR "Talent Acquisition")'
    
    payload = json.dumps({"q": query, "gl": "it", "hl": "it"})
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code != 200: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        risultati = res.json().get('organic', [])
        if not risultati: return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        
        testo_risultati = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in risultati[:5]])
        
        prompt = f"""
        Analizza questi profili LinkedIn.
        Azienda: '{nome_azienda}'
        Email info: '{email_generica}', Dominio: '{dominio}'
        
        Trova UN SOLO Decision Maker (es. Titolare, CEO, Direttore Commerciale o HR). Deduci l'email diretta.
        
        Rispondi ESATTAMENTE su una sola riga: NOME E COGNOME | RUOLO | EMAIL_D
