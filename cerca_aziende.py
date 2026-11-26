import os
import sys
import json
import random
import time
import re
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
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
URL_FOGLIO = "https://docs.google.com/spreadsheets/d/15K6_SNBTB-QBNwFB2L6Qjrd56wZ7clD3Tm9zM-MI7zc/edit?gid=0#gid=0"

try:
    sh = gc.open_by_url(URL_FOGLIO)
    worksheet = sh.sheet1
    worksheet_prospect = sh.worksheet("Nuovi Prospect")
except Exception as e:
    print(f"Errore di connessione al foglio: {e}")
    sys.exit(1)

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
    '"ampliamento rete vendita"',
    '"mandato di agenzia" "lavora con noi"',
    '"inquadramento enasarco"',
    '"venditori a partita iva"',
    '"commerciali p.iva"',
    '"tecnico commerciale" "enasarco"',
    '"agente plurimandatario"',
    '"potenziamento rete vendita"',
    '"inserimento agenti"',
    'inurl:lavora-con-noi "agenti"',
    'inurl:lavora-con-noi "enasarco"',
    'inurl:collabora-con-noi "agenti"',
    'inurl:ricerca-agenti',
    'inurl:diventa-agente',
    'inurl:posizioni-aperte "agente"',
    'intitle:"lavora con noi" "agenti"',
    'intitle:"ricerca agenti"',
    'intitle:"cerchiamo agenti"'
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
    "dispositivi medici", "ortopedia", "cartotecnica", "etichettificio", "vernici",
    "imballaggi", "refrigerazione", "climatizzazione", "pneumatica", "valvole",
    "rubinetteria", "ceramiche", "pavimenti", "rivestimenti", "isolanti",
    "colorificio", "adesivi", "sigillanti", "abrasivi", "saldatura",
    "compressori", "carrelli elevatori", "scaffalature", "arredo bagno",
    "arredo ufficio", "contract", "forniture alberghiere", "ristorazione",
    "surgelati", "panificazione", "pasticceria", "caffe", "torrefazione",
    "integratori", "nutraceutica", "farmaceutico", "forniture dentali",
    "prodotti veterinari", "pet food", "zootecnia", "fertilizzanti", "sementi",
    "enologia", "oleificio", "conserve", "salumificio", "caseificio",
    "tessile", "abbigliamento da lavoro", "calzaturificio", "pelletteria",
    "occhialeria", "galvanica", "fonderia", "torneria", "lavorazioni meccaniche",
    "lamiere", "profilati", "alluminio", "acciaio", "materie plastiche",
    "gomma", "guarnizioni", "cavi elettrici", "quadri elettrici", "sensoristica",
    "strumentazione", "laboratorio", "depurazione", "trattamento acque",
    "ecologia", "antincendio", "videosorveglianza", "controllo accessi",
    "gestionale", "erp", "stampa digitale", "flessografia", "espositori"
]

province = [
    "Milano", "Brescia", "Verona", "Torino", "Bologna", "Roma", "Padova", "Vicenza",
    "Treviso", "Bergamo", "Firenze", "Napoli", "Varese", "Monza", "Como", "Modena",
    "Parma", "Reggio Emilia", "Cuneo", "Udine", "Pordenone", "Lecco", "Novara",
    "Mantova", "Cremona", "Piacenza", "Rimini", "Ancona", "Bari", "Forlì", "Cesena",
    "Ravenna", "Ferrara", "Pesaro", "Macerata", "Ascoli Piceno", "Fermo", "Perugia",
    "Terni", "Arezzo", "Lucca", "Pisa", "Prato", "Pistoia", "Siena", "Genova",
    "Alessandria", "Asti", "Biella", "Vercelli", "Pavia", "Lodi", "Sondrio",
    "Trento", "Bolzano", "Belluno", "Rovigo", "Venezia", "Trieste", "Gorizia",
    "Pescara", "Chieti", "Teramo", "Latina", "Frosinone", "Viterbo", "Caserta",
    "Salerno", "Avellino", "Benevento", "Foggia", "Barletta", "Taranto", "Brindisi",
    "Lecce", "Catania", "Palermo", "Messina", "Ragusa", "Siracusa", "Cagliari",
    "Sassari", "Lombardia", "Veneto", "Emilia Romagna", "Piemonte", "Toscana",
    "Marche", "Friuli", "Puglia", "Campania", "Sicilia", "Abruzzo", "Umbria"
]

# Controllato SOLO sul dominio (netloc), mai sul percorso interno dell'URL
domini_da_escludere = (
    'indeed.', 'infojobs.', 'linkedin.', 'subito.', 'cercoagente.', 'venditori.it',
    'venditori.com', 'bakeca.', 'glassdoor.', 'jooble.', 'monster.', 'wikihow.',
    'wikipedia.', 'youtube.', 'lavoro.it', 'jobeka.', 'applavoro.', 'jobsora.',
    'rappresentanti.it', 'startup.jobs', 'jobijoba.', 'trabajo.', 'gigroup.',
    'randstad.', 'grafton.', 'adecco.', 'manpower.', 'generazionevincente.',
    'trovolavoro.', 'corriere.', 'annunci.it', 'bancalavoro.', 'jobgratis.',
    'cornerjob.', 'aliagenzia.', 'synergie-', 'pagepersonnel.', 'michaelpage.',
    'hays.', 'quojobis.', 'orienta.net', 'maw.it', 'inhrgroup.', 'careerjet.',
    'impiego24.', 'lavorofacile.', 'ialweb.', 'bachecalavoro.', 'jobrapido.',
    'cercolavoro.', 'simplyhired.', 'altamiraweb.', 'inrecruiting.', 'niuma.',
    'cving.', 'talent.com', 'openjobmetis.', 'agentscout.', 'jobleads.',
    'whatjobs.', 'cercoagenti.', 'federagenti.', 'camcom.', 'ascom.', 'kijiji.',
    'mitula.', 'neuvoo.', 'adzuna.', 'trovit.', 'tuolavoro.', 'fashionjobs.',
    'fashionjob.it', 'risorse.it', 'lifein.', 'instagram.', 'facebook.', 'tiktok.',
    'bancaclv.', 'agenti.com', 'lavoropiu.', 'jobbydoo.', 'areajob.', 'clickajobs.',
    'jobsavior.', 'tuoagente.', 'ilcommerciale.', 'ucv.online', 'guru.jobs',
    'enasarco.it', 'fnaarc.', 'usarci.', 'unimpiego.', 'fiscozen.', 'assolombarda.',
    'regione.', 'provincia.', 'comune.', 'agentitreviso.', 'inmatch.', 'allibo.',
    'cgil.', 'cisl.', 'uil.', 'confcommercio.', 'confartigianato.', 'confindustria.',
    'cna.it', 'jobiri.', 'livecareer.', 'onlinecv.', 'modelli-di-curriculum.',
    'ticonsiglio.', 'hrspecialistitalia.', 'profiliecarriere.', 'samsic-hr.',
    'lavorai.', 'joinrs.', 'intervieweb.', 'giurcost.', 'esselungajob.',
    'nettowork.', 'bebee.', 'umana.it', 'studiostella.', 'studiogiudice.',
    'saviglianoformazione.', 'telecomitalia.', 'expertini.', 'lavoroeconcorsi.',
    'jobssjob.', 'recruit.net', 'agentworkhub.', 'teamtailor.', 'oraclecloud.',
    'carusihr.', 'casa.it', 'immobiliare.', 'tecnocasa.', 'tempocasa.', 'gabetti.',
    'remax.', 'toscano.it', 'engelvoelkers.', 'paginebianche.', 'paginegialle.',
    'verisure.', 'venditoriadistanza.', 'x.com', 'twitter.com', 'just.it',
    'reddit.com', 'calameo.com', 'faciletrovare.', 'atoka.io', 'empresite.',
    'pornhub.', 'xhamster.', 'bokep', 'porndig.', 'assinews.', 'realemutua.',
    'groupama.', 'unipol', 'allianz.', 'generali.', 'grandiscuole.it',
    'cepulavoro.', 'issuu.com', 'archive.org', 'gowork.it', 'casagenti.it',
    'vorwerk.com', 'studocu.com', 'halleyweb.com', 'mondobirra.org', 'manstar',
    'kompass', 'europages', 'informazione-aziende', 'ufficiocamerale',
    'fatturatoitalia', 'signalhire', 'rocketreach', 'zoominfo', 'dnb.com',
    'crunchbase', '.edu.it', '.gov.it', 'unibo.it', 'unito.it', 'uniroma',
    'polimi.it', 'aulab.it', 'radiogold.it', 'foodcareer.it', 'lavoraconnoi.com',
    'gazzettadellavoro.com', 'globelife.com', '360forma.com', 'xing.com',
    'academia.edu', 'professioneagente.it', 'go2sales.it', 'tutto626.it',
    'claude.com', 'job4italy.com', 'trendsrl.net', 'profili.it', 'gesacom.it',
    'federprivacy.org', 'affida.credit', 'credipass.it', 'sellapersonalcredit.it',
    'vivienergia.it', 'jimdoweb.com', 'webnode.it', 'webnode.page', 'wixsite.com',
    'altervista.org', 'made-in-china.com', 'alibaba.com', 'agriaffaires.',
    'machineryzone.', 'noleggiamoauto.it', 'senato.it', 'virgilio.it', 'leggo.it',
    'mattinopadova.it', 'elledecor.com', 'github.com', 'infobel.com',
    'openedition.org', 'legambiente.it', 'ny.gov', 'agent321.', 'freshplaza.it',
    'ricercaimprese.com', 'partitaiva24.it', 'italiaatavola.net',
    'informazionesenzafiltro.it', 'eventipress.com', 'studiolegale', 'avvocato',
    'commercialista', 'consulentedellavoro', 'studiodentistico', 'dentista',
    'clinicaveterinaria', 'veterinari', 'farmacia', 'parafarmacia',
    'gdonews.it', 'infowine.com', 'mecspe.com', 'wewelfare.it', 'repubblica.it',
    'ilsole24ore.com', 'milano.zone', 'today.it', 'fanpage.it', 'ansa.it',
    'adnkronos.com', 'art-er.it', 'clust-er.it', 'pharmapoint.it', 'benetton.com'
)

# Controllato SOLO sul path dell'URL (sblocca /azienda/, /company/, /corporate/, careers.)
path_da_escludere = (
    '/sitemap', '/category/', '/tag/', '/author/', '/economia/', '/cronaca/',
    '/politica/', '/elezioni/', '/incontri', '/cookie-policy', '/privacy-policy',
    '/cookie', '/privacy', '/termini-e-condizioni', '/condizioni-di-vendita',
    '/investors/', '/shop/', '/carrello', '/checkout', '/product/', '/products/',
    '/catalogo/', '/case-study/', '/caso-studio/', '/punti-vendita',
    '/trova-rivendit', '/rivenditori', '/account/', '/login', '/register',
    '/magazine/', '/eventi/', '/evento/', '/fiere/', '/normativa', '/aliquote',
    '/calcolo-', '/guida-', '/come-diventare', '/chi-e-l-agente',
    '/companies/', '/aziende/', '/directory/'
)

TLD_ESTERI_DA_BLOCCARE = (
    '.cn', '.ae', '.ru', '.in', '.tr', '.pl', '.ro', '.br', '.mx', '.uk', '.us', '.gov', '.edu'
)

def estrai_dominio(testo_url):
    if not testo_url:
        return ""
    t = testo_url.strip().lower()
    if "://" in t:
        netloc = urlparse(t).netloc
    else:
        netloc = t.split('/')[0]
    netloc = netloc.split(':')[0]
    return re.sub(r'^(www\d*\.|it\.|careers\.|jobs\.|lavoro\.)', '', netloc)

def ha_segnali_reali_ricerca_agenti(titolo, snippet, link):
    testo_completo = f"{titolo} {snippet} {link}".lower()

    # Esclusioni con confini di parola (\b) per non bloccare mai parole valide come 'selezioniamo'
    pattern_esclusioni = (
        r'\b(agenti\s+ai|agente\s+ai|agenti\s+ia|agenti\s+digitali|agentic|'
        r'intelligenza\s+artificiale|agenti\s+patogeni|agenti\s+chimici|'
        r'agenti\s+cancerogeni|agenti\s+atmosferici|agenti\s+fisici|'
        r'agenti\s+sbiancanti|agente\s+sbiancante|agenti\s+infettivi|'
        r'agenti\s+addensanti|agenti\s+pulenti|agenti\s+esterni|'
        r'agenti\s+immobiliari|agente\s+immobiliare|mediazione\s+creditizia|'
        r'agente\s+in\s+attivit[aà]\s+finanziaria|agente\s+assicurativo|subagente|'
        r'aliquote\s+enasarco|calcolo\s+enasarco|aprire\s+partita\s+iva|'
        r'codice\s+ateco|concorso\s+pubblico|agenti\s+di\s+polizia|agenti\s+municipali|'
        r'sindacato\s+autonomo\s+di\s+polizia|elezioni\s+comunali|elezioni\s+regionali|'
        r'candidato\s+sindaco|liste\s+a\s+sostegno|cookie\s+policy|informativa\s+privacy|'
        r'aggiungi\s+al\s+carrello|spedizione\s+gratuita|sbiancamento\s+dentale)\b'
    )
    if re.search(pattern_esclusioni, testo_completo):
        return False

    pattern_ruolo = (
        r'\b(agente|agenti|rappresentante|rappresentanti|procacciatore|procacciatori|'
        r'plurimandatario|plurimandatari|monomandatario|monomandatari|enasarco|'
        r'venditore|venditori|rete[\s\-]+vendita|forza[\s\-]+vendita|sales[\s\-]+agent)\b'
    )
    if not re.search(pattern_ruolo, testo_completo):
        return False

    pattern_selezione = (
        r'(lavora[\s\-]+con[\s\-]+noi|lavoraconnoi|collabora[\s\-]+con[\s\-]+noi|'
        r'cerchiamo|cercasi|ricerca[\s\-]+agent|ricerca[\s\-]+rappresentant|'
        r'ricerca[\s\-]+vendit|ricerchiamo|selezioniamo|selezione[\s\-]+agent|'
        r'candidatura|candidati|invia[\s\-]+il[\s\-]+cv|invia[\s\-]+curriculum|'
        r'curriculum|diventa[\s\-]+agente|diventa[\s\-]+nostro|posizioni[\s\-]+aperte|'
        r'opportunit[aà][\s\-]+di[\s\-]+lavoro|opportunit[aà][\s\-]+professional|'
        r'carriere|careers|ampliamento[\s\-]+rete|potenziamento[\s\-]+rete|'
        r'mandato[\s\-]+di[\s\-]+agenzia|inquadramento[\s\-]+enasarco)'
    )
    if not re.search(pattern_selezione, testo_completo):
        return False

    return True

def main():
    TARGET_NUOVI_ANNUNCI = 120
    MAX_QUERIES = 125

    colonna_b_master = worksheet.col_values(2)
    colonna_b_prospect = worksheet_prospect.col_values(2)

    domini_inseriti = set()
    for link in colonna_b_master[1:] + colonna_b_prospect[1:]:
        if link:
            dominio = estrai_dominio(link)
            if dominio:
                domini_inseriti.add(dominio)

    print(f"Domini storici già in archivio (anti-duplicato): {len(domini_inseriti)}")

    dati_da_inserire = []
    combinazioni_usate = set()

    esclusioni_q = '-immobiliare -assicurazioni -luce -gas -subito -indeed -linkedin -"agenti ai"'

    for idx_q in range(1, MAX_QUERIES + 1):
        azione = random.choice(azioni)
        settore = random.choice(settori)
        provincia = random.choice(province)
        pagina = random.choice([1, 1, 1, 2])

        modalita = random.choice([1, 2, 3, 4, 5])
        if modalita == 1:
            query_base = f'{azione} {settore}'
        elif modalita == 2:
            query_base = f'{azione} {provincia}'
        elif modalita == 3:
            query_base = f'{azione} {settore} {provincia}'
        elif modalita == 4:
            query_base = f'{azione} {provincia} (srl OR spa)'
        else:
            query_base = f'site:.it {azione} {settore}'

        chiave_combo = f"{query_base}_{pagina}"
        if chiave_combo in combinazioni_usate:
            continue
        combinazioni_usate.add(chiave_combo)

        query = f'{query_base} {esclusioni_q}'
        print(f"[{idx_q}/{MAX_QUERIES}] Query (Pag. {pagina}): {query}")

        url = "https://google.serper.dev/search"
        payload_dict = {
            "q": query,
            "gl": "it",
            "hl": "it",
            "num": 20
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
                print("Crediti Serper esauriti. Interrompo la ricerca.")
                break

            if response.status_code == 400 and ("page" in payload_dict or "num" in payload_dict):
                payload_dict.pop("num", None)
                payload_dict.pop("page", None)
                response = requests.post(url, headers=headers, data=json.dumps(payload_dict), timeout=15)

            response.raise_for_status()
            data = response.json()

            risultati = data.get('organic', [])
            if not risultati:
                time.sleep(0.7)
                continue

            for item in risultati:
                titolo = (item.get('title') or 'Sito Aziendale').strip()
                snippet = (item.get('snippet') or '').strip()
                link_originale = (item.get('link') or '').strip()
                link = link_originale.lower()

                if not link or link.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.zip')):
                    continue

                parsed_url = urlparse(link)
                netloc_raw = parsed_url.netloc.split(':')[0]
                path_url = parsed_url.path or '/'

                if netloc_raw.endswith(TLD_ESTERI_DA_BLOCCARE):
                    continue

                dominio_estratto = estrai_dominio(link)
                if not dominio_estratto or dominio_estratto in domini_inseriti:
                    continue

                if any(dom_vietato in netloc_raw for dom_vietato in domini_da_escludere):
                    continue

                if any(path_vietato in path_url for path_vietato in path_da_escludere):
                    continue

                if not ha_segnali_reali_ricerca_agenti(titolo, snippet, link):
                    continue

                dati_da_inserire.append([titolo, link_originale])
                domini_inseriti.add(dominio_estratto)

                if len(dati_da_inserire) >= TARGET_NUOVI_ANNUNCI:
                    break

        except requests.exceptions.HTTPError as err:
            print(f"Errore HTTP da Serper: {err}")
        except Exception as e:
            print(f"Errore ricerca: {e}")

        if len(dati_da_inserire) >= TARGET_NUOVI_ANNUNCI:
            break

        time.sleep(0.8)

    if dati_da_inserire:
        try:
            worksheet.append_rows(dati_da_inserire, value_input_option='USER_ENTERED')
            print(f"Aggiunti con successo {len(dati_da_inserire)} nuovi annunci REALI di ricerca agenti!")
        except Exception as e_sheet:
            print(f"Errore durante il salvataggio su Google Sheet: {e_sheet}")
    else:
        print("Nessun nuovo prospect trovato in questa sessione.")

if __name__ == "__main__":
    main()
