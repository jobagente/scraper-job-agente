import os
import sys
import json
import random
import time
import requests
import gspread
from urllib.parse import urlparse
from google.oauth2.service_account import Credentials

# Forza la stampa immediata nei log di GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

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
    exit(1)

# Tutte le query forzano la presenza di una pagina di selezione/ricerca agenti
azioni = [
    '"lavora con noi" "agenti"',
    '"lavora con noi" "agente di commercio"',
    '"cerchiamo agenti"',
    '"ricerca agenti"',
    '"cercasi agenti"',
    '"selezioniamo agenti"',
    '"diventa nostro agente"',
    '"collabora con noi" "agenti"',
    '"invia cv" "agente"',
    '"ampliamento rete vendita" "agenti"',
    '"agenti plurimandatari" "lavora con noi"',
    '"agenti monomandatari" "lavora con noi"',
    '"ricerca rappresentanti"',
    '"ricerca procacciatori"'
]

settori = [
    "medicale", "software", "horeca", "edilizia", "industriale", "b2b",
    "automazione", "logistica", "alimentare", "servizi alle imprese", 
    "arredamento", "impiantistica", "cosmesi", "meccanica", "agricoltura", 
    "ferramenta", "packaging", "plastica", "chimica", "utensileria", 
    "termoidraulica", "illuminazione", "serramenti", "antinfortunistica", 
    "forniture industriali", "macchinari", "oleodinamica", "elettrotecnica",
    "carpenteria", "stampaggio", "automazione industriale", "detergenza"
]

province = [
    "Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", 
    "Treviso", "Bergamo", "Firenze", "Napoli", "Varese", "Monza", "Como", "Modena", 
    "Parma", "Reggio Emilia", "Cuneo", "Udine", "Pordenone", "Lecco", "Novara",
    "Mantova", "Cremona", "Piacenza", "Rimini", "Ancona", "Bari", "Italia"
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
    'verisure', 'venditoriadistanza', 'x.com', 'twitter.com', '.blog/',
    'commercialagents-italy', 'just.it', 'reddit.com', 'calameo.com', 'faciletrovare',
    'atoka.io', 'empresite', 'pornhub', 'xhamster', 'bokep', 'porndig', 'assinews',
    'realemutua', 'groupama', 'unipol', 'allianz', 'generali'
]

# Esclude pagine di catalogo prodotti, case study, news o ricerca rivenditori per clienti finali
path_da_escludere = [
    '/sitemap', '/blog/', '/news/', '/category/', '/tag/', '/author/', 
    '/articolo/', '/economia/', '/storia-', '/incontri', '/global/', 
    '/corporate/', '/investors/', 'careers.', 'jobs.', '/prodotti/', 
    '/product/', '/portfolio/', '/case-study/', '/caso-studio/', 
    '/punti-vendita', '/trova-rivendit', '/account/'
]

def estrai_dominio(testo_url):
    if not testo_url: return ""
    t = testo_url.strip().lower()
    if "://" in t:
        return urlparse(t).netloc.replace('www.', '')
    return t.split('/')[0].replace('www.', '')

def ha_segnali_reali_ricerca_agenti(titolo, snippet, link):
    """Verifica che il risultato di Google contenga davvero un annuncio/ricerca di agenti o lavora con noi."""
    testo_completo = f"{titolo} {snippet} {link}".lower()
    
    # 1. Deve esserci un riferimento alla figura commerciale/agente
    parole_target = ['agent', 'rappresentant', 'procacciat', 'vendit', 'commercial', 'plurimandat', 'monomandat', 'enasarco']
    if not any(pt in testo_completo for pt in parole_target):
        return False
        
    # 2. Deve esserci un segnale di selezione/candidatura aperta (nella URL, nel titolo o nello snippet)
    segnali_selezione = [
        'lavora con noi', 'lavora-con-noi', 'lavoraconnoi', 'carriere', 'careers',
        'cerchiamo', 'cercasi', 'ricerca agent', 'ricerca rappresentant', 'ricerca procacciat',
        'ricerca commercial', 'ricerca vendit', 'selezioniamo', 'selezione', 'candidat', 
        'invia cv', 'invia il tuo cv', 'curriculum', 'diventa nostro agente', 'diventa agente',
        'collabora con noi', 'collabora-con-noi', 'posizioni aperte', 'posizione aperta',
        'opportunità di lavoro', 'opportunità per agent', 'ampliamento rete', 'entrare nella rete'
    ]
    if not any(ss in testo_completo for ss in segnali_selezione):
        return False
        
    return True

def main():
    colonna_b_master = worksheet.col_values(2)
    colonna_b_prospect = worksheet_prospect.col_values(2)
    
    domini_inseriti = set()
    for link in colonna_b_master[1:] + colonna_b_prospect[1:]:
        if link:
            dominio = estrai_dominio(link)
            if dominio:
                domini_inseriti.add(dominio)
            
    dati_da_inserire = []
    combinazioni_usate = set()

    for _ in range(55):
        azione = random.choice(azioni)
        settore = random.choice(settori)
        provincia = random.choice(province)
        # Pagine 1 e 2 per evitare che Google ignori le virgolette su pagine troppo profonde
        pagina = random.choice([1, 2])
        
        chiave_combo = f"{azione}_{settore}_{provincia}_{pagina}"
        if chiave_combo in combinazioni_usate:
            continue
        combinazioni_usate.add(chiave_combo)
        
        query = f'{azione} {settore} {provincia} -immobiliare -assicurazioni -franchising -concorso'
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
            
            if response.status_code == 400 and "Not enough credits" in response.text:
                print("⚠️ Crediti Serper esauriti. Interrompo la ricerca.")
                break
                
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
                snippet = item.get('snippet', '')
                link_originale = item.get('link', '')
                link = link_originale.lower()
                
                if not link or link.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    continue
                    
                titolo_lower = titolo.lower()
                if any(p in titolo_lower for p in ['immobiliare', 'incontri', 'cerco ragazza', 'trans ', 'concorso pubblico', 'multinazionale', 'bokep', 'porn']):
                    continue
                    
                if any(path_vietato in link for path_vietato in path_da_escludere):
                    continue
                
                # CONTROLLO DI PERTINENZA: Salva il link solo se parla davvero di ricerca/selezione agenti o Lavora con noi
                if not ha_segnali_reali_ricerca_agenti(titolo, snippet, link):
                    continue
                    
                dominio_estratto = estrai_dominio(link)
                
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
        try:
            worksheet.append_rows(dati_da_inserire, value_input_option='USER_ENTERED')
            print(f"✅ Aggiunti con successo {len(dati_da_inserire)} annunci REALI di ricerca agenti!")
        except Exception as e_sheet:
            print(f"⚠️ Errore durante il salvataggio su Google Sheet: {e_sheet}")
    else:
        print("Nessun nuovo prospect trovato in questa sessione.")

if __name__ == "__main__":
    main()
