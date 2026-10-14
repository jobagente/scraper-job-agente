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
    worksheet_prospect = sh.worksheet("Nuovi Prospect")
except Exception as e:
    print(f"Errore di connessione al foglio: {e}")
    exit()

azioni = [
    '"ricerca agenti"', '"cerchiamo agenti"', '"selezioniamo agenti"', 
    '"lavora con noi" agente', '"posizioni aperte" agente', 
    '"ricerca procacciatori"', '"invia cv" agente', '"rete vendita" "lavora con noi"',
    '"opportunità per agenti"', '"ricerca rappresentanti"', '"agenti plurimandatari"',
    '"agenti monomandatari"', '"ampliamento rete vendita"', '"cerca agenti"'
]

settori = [
    "medicale", "software", "horeca", "edilizia", "industriale", "b2b",
    "farmaceutico", "automazione", "logistica", "alimentare", "servizi alle imprese", 
    "arredamento", "impiantistica", "cosmesi", "meccanica", "agricoltura", 
    "ferramenta", "packaging", "plastica", "chimica", "utensileria", 
    "termoidraulica", "illuminazione", "serramenti", "antinfortunistica", 
    "forniture industriali", "macchinari", "oleodinamica", "elettrotecnica"
]

province = [
    "Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", 
    "Treviso", "Bergamo", "Firenze", "Napoli", "Varese", "Monza", "Como", "Modena", 
    "Parma", "Reggio Emilia", "Cuneo", "Udine", "Pordenone", "Lecco", "Novara",
    "Mantova", "Cremona", "Piacenza", "Rimini", "Ancona", "Bari", "Busto Arsizio"
]

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
    'risorse.it', 'lifein', 'instagram', 'facebook', 'tiktok', 'bancaclv',
    'agenti.com', 'lavoropiu', 'jobbydoo', 'areajob', 'clickajobs', 'jobsavior', 
    'tuoagente', 'ilcommerciale', 'ucv.online', 'guru.jobs', 'enasarco.it', 
    'fnaarc', 'usarci', 'unimpiego', 'fiscozen', 'assolombarda', 'regione.', 
    'agentitreviso', 'inmatch', 'allibo', 'cgil', 'cisl', 'uil', 'confcommercio',
    'jobiri', 'livecareer', 'onlinecv', 'modelli-di-curriculum', 'ticonsiglio',
    'hrspecialistitalia', 'profiliecarriere', 'samsic-hr', 'lavorai', 'joinrs',
    'intervieweb', 'provincia.', 'giurcost', 'esselungajob',
    'nettowork', 'bebee', 'umana', 'studiostella', 'studiogiudice', 
    'saviglianoformazione', 'comune.', 'business.telecomitalia.it',
    'expertini', 'lavoroeconcorsi', 'jobssjob', 'recruit.net', 'agentworkhub',
    'teamtailor', 'oraclecloud', 'carusihr', 'confartigianato', 'confindustria',
    'cna.it', 'casa.it', 'immobiliare', 'tecnocasa', 'tempocasa', 'gabetti',
    'remax', 'toscano.it', 'engelvoelkers', 'paginebianche', 'paginegialle',
    'verisure', 'venditoriadistanza', 'x.com', 'twitter.com', '.blog/'
]

path_da_escludere = [
    '/sitemap', '/blog/', '/news/', '/category/', '/tag/', '/author/', 
    '/articolo/', '/economia/', '/storia-', '/incontri'
]

def main():
    colonna_b_master = worksheet.col_values(2)
    colonna_b_prospect = worksheet_prospect.col_values(2)
    prima_riga_vuota = len(colonna_b_master) + 1
    
    # CONTROLLO ANTI-DOPPIONI: legge i domini sia da Foglio1 sia da Nuovi Prospect
    domini_inseriti = set()
    for link in colonna_b_master[1:] + colonna_b_prospect[1:]:
        if link:
            dominio = urlparse(link.strip()).netloc.replace('www.', '').lower()
            if dominio:
                domini_inseriti.add(dominio)
            
    dati_da_inserire = []
    combinazioni_usate = set()

    for _ in range(65):
        azione = random.choice(azioni)
        settore = random.choice(settori)
        provincia = random.choice(province)
        pagina = random.choice([1, 2])
        
        chiave_combo = f"{azione}_{settore}_{provincia}_{pagina}"
        if chiave_combo in combinazioni_usate:
            continue
        combinazioni_usate.add(chiave_combo)
        
        query = f'{azione} {settore} {provincia} -immobiliare -franchising -associazione -corsi'
        print(f"Eseguo query mirata (Pag. {pagina}): {query}")
        
        url = "https://google.serper.dev/search"
        payload_dict = {
            "q": query,
            "gl": "it",
            "hl": "it"
        }
        if pagina > 1:
            payload_dict["page"] = pagina
            
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload_dict), timeout=15)
            if response.status_code == 400 and "page" in payload_dict:
                del payload_dict["page"]
                response = requests.post(url, headers=headers, data=json.dumps(payload_dict), timeout=15)
                
            response.raise_for_status()
            data = response.json()
            
            risultati = data.get('organic', [])
            if not risultati:
                print("Nessun risultato utile.")
                time.sleep(2)
                continue
            
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                link_originale = item.get('link', '')
                link = link_originale.lower()
                
                if not link or link.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    continue
                    
                titolo_lower = titolo.lower()
                if any(p in titolo_lower for p in ['immobiliare', 'incontri', 'cerco ragazza', 'trans ', 'concorso pubblico']):
                    continue
                    
                if any(path_vietato in link for path_vietato in path_da_escludere):
                    continue
                    
                dominio_estratto = urlparse(link).netloc.replace('www.', '').lower()
                
                if not any(sito_vietato in link for sito_vietato in siti_da_escludere):
                    if dominio_estratto and dominio_estratto not in domini_inseriti:
                        dati_da_inserire.append([titolo, link_originale])
                        domini_inseriti.add(dominio_estratto)
                
                if len(dati_da_inserire) >= 100:
                    break
                    
        except requests.exceptions.HTTPError as err:
            print(f"Errore HTTP da Serper: {err} - Risposta: {response.text}")
        except Exception as e:
            print(f"Errore ricerca: {e}")
            
        if len(dati_da_inserire) >= 100:
            break
            
        time.sleep(2)

    if dati_da_inserire:
        intervallo = f"A{prima_riga_vuota}:B{prima_riga_vuota + len(dati_da_inserire) - 1}"
        worksheet.update(values=dati_da_inserire, range_name=intervallo)
        print(f"Aggiunti {len(dati_da_inserire)} prospect mandanti puliti!")
    else:
        print("Nessun nuovo prospect trovato in questa sessione.")

if __name__ == "__main__":
    main()
