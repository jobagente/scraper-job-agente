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

azioni = [
    '"lavora con noi" "agenti"',
    '"lavora con noi" "agente di commercio"',
    '"cerchiamo agenti"',
    '"ricerca agenti"',
    '"cercasi agenti"',
    '"selezioniamo agenti"',
    '"diventa nostro agente"',
    '"collabora con noi" "agenti"',
    '"agenti plurimandatari"',
    '"agenti monomandatari"',
    '"ricerca rappresentanti"',
    '"ricerca procacciatori"',
    '"ampliamento rete vendita" "agenti"',
    'inurl:lavora-con-noi "agenti"',
    'intitle:"lavora con noi" "agenti"'
]

settori = [
    "medicale", "software", "horeca", "edilizia", "industriale", "b2b",
    "automazione", "logistica", "alimentare", "servizi alle imprese", 
    "arredamento", "impiantistica", "cosmesi", "meccanica", "agricoltura", 
    "ferramenta", "packaging", "plastica", "chimica", "utensileria", 
    "termoidraulica", "illuminazione", "serramenti", "antinfortunistica", 
    "forniture industriali", "macchinari", "oleodinamica", "elettrotecnica",
    "carpenteria", "stampaggio", "automazione industriale", "detergenza",
    "estetica professionale", "ricambi", "componentistica", "bevande", "vini",
    "medical devices", "ortopedia", "cartotecnica", "etichettificio", "vernici"
]

province = [
    "Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza", 
    "Treviso", "Bergamo", "Firenze", "Napoli", "Varese", "Monza", "Como", "Modena", 
    "Parma", "Reggio Emilia", "Cuneo", "Udine", "Pordenone", "Lecco", "Novara",
    "Mantova", "Cremona", "Piacenza", "Rimini", "Ancona", "Bari", "Lombardia", 
    "Veneto", "Emilia Romagna", "Piemonte", "Toscana", "Marche"
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
    'realemutua', 'groupama', 'unipol', 'allianz', 'generali', 'grandiscuole.it', 
    'cepulavoro', 'issuu.com', 'archive.org', 'gowork.it', 'casagenti.it', 'vorwerk.com',
    'studocu.com', 'halleyweb.com', 'mondobirra.org', 'manstar', 'kompass', 
    'europages', 'informazione-aziende', 'ufficiocamerale', 'fatturatoitalia', 
    'signalhire', 'rocketreach', 'zoominfo', 'dnb.com', 'crunchbase',
    '.edu.it', '.gov.it', 'lavoraconnoi.com', 'gazzettadellavoro.com', 'globelife.com', 
    '360forma.com', 'xing.com', 'academia.edu', 'professioneagente.it', 'go2sales.it',
    'tutto626.it', 'claude.com', 'job4italy.com', 'trendsrl.net', 'profili.it',
    'gesacom.it', 'federprivacy.org', 'affida.credit', 'credipass.it',
    'sellapersonalcredit.it', 'vivienergia.it', 'trasparenza-valutazione-merito.it'
]

path_da_escludere = [
    '/sitemap', '/blog/', '/news/', '/category/', '/tag/', '/author/', 
    '/articolo/', '/economia/', '/storia-', '/incontri', '/global/', 
    '/corporate/', '/investors/', 'careers.', 'jobs.', '/prodotti/', 
    '/product/', '/portfolio/', '/case-study/', '/caso-studio/', 
    '/punti-vendita', '/trova-rivendit', '/account/', '/magazine/',
    '/companies/', '/company/', '/aziende/', '/azienda/', '/directory/', '/profile/'
]

def estrai_dominio(testo_url):
    if not testo_url: return ""
    t = testo_url.strip().lower()
    if "://" in t:
        return urlparse(t).netloc.replace('www.', '')
    return t.split('/')[0].replace('www.', '')

def ha_segnali_reali_ricerca_agenti(titolo, snippet, link):
    testo_completo = f"{titolo} {snippet} {link}".lower()
    
    # Blocca articoli che parlano di "agenti AI" / intelligenza artificiale o agenti patogeni/chimici
    if any(escl in testo_completo for escl in ['agenti ai', 'agente ai', 'agenti ia', 'intelligenza artificiale', 'agenti patogeni', 'agenti chimici', 'agenti cancerogeni']):
        return False
    
    # Esclude pagine che sono palesemente homepage/cataloghi senza alcun cenno a lavoro o agenti
    parole_target = ['agent', 'rappresentant', 'procacciat', 'vendit', 'commercial', 'plurimandat', 'monomandat', 'enasarco']
    if not any(pt in testo_completo for pt in parole_target):
        return False
        
    segnali_selezione = [
        'lavora', 'job', 'carriere', 'careers', 'cerchiamo', 'cercasi', 
        'ricerca', 'ricerchiamo', 'selezion', 'candidat', 'invia', 'curriculum', 
        'diventa', 'collabora', 'posizion', 'opportunità', 'ampliamento', 
        'inserimento', 'plurimandat', 'monomandat', 'enasarco', 'mandato'
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

    # 85 ricerche bilanciate tra Settore, Area Geografica e Pagine 1-4 per scavalcare i domini già noti
    for _ in range(85):
        azione = random.choice(azioni)
        settore = random.choice(settori)
        provincia = random.choice(province)
        pagina = random.choice([1, 2, 3, 4])
        
        modalita = random.choice([1, 2, 3])
        if modalita == 1:
            # Ricerca per Azione + Settore su tutta Italia (altissima resa di annunci reali)
            query_base = f'{azione} {settore}'
        elif modalita == 2:
            # Ricerca per Azione + Settore + Provincia/Regione
            query_base = f'{azione} {settore} {provincia}'
        else:
            # Ricerca PMI per Azione + Provincia/Regione + Srl/Spa
            query_base = f'{azione} {provincia} (srl OR spa)'
            
        chiave_combo = f"{query_base}_{pagina}"
        if chiave_combo in combinazioni_usate:
            continue
        combinazioni_usate.add(chiave_combo)
        
        query = f'{query_base} -immobiliare -assicurazioni -franchising -concorso -subito -indeed -"agenti ai"'
        print(f"Eseguo query (Pag. {pagina}): {query}")
        
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
                time.sleep(1.2)
                continue
            
            for item in risultati:
                titolo = item.get('title', 'Sito Aziendale')
                snippet = item.get('snippet', '')
                link_originale = item.get('link', '')
                link = link_originale.lower()
                
                if not link or link.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    continue
                    
                titolo_lower = titolo.lower()
                if any(p in titolo_lower for p in ['immobiliare', 'incontri', 'cerco ragazza', 'trans ', 'concorso pubblico', 'multinazionale', 'bokep', 'porn', 'agenti ai', 'intelligenza artificiale']):
                    continue
                    
                if any(path_vietato in link for path_vietato in path_da_escludere):
                    continue
                
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
            
        time.sleep(1.2)

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
