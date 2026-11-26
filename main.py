def pulisci_nome_azienda(nome):
    if not nome:
        return ""
    # Rimuove eventuali prefissi ripetuti dal modello (es. "NOME_AZIENDA:")
    n = re.sub(r'(?i)^nome[_\s]*azienda\s*[:\-]\s*', '', str(nome).strip())
    # Rimuove forme societarie con o senza punti finali (senza \b dopo il punto!)
    pat = (
        r'(?i)(?<![a-z0-9])(s\.?\s*r\.?\s*l\.?\s*s\.?|s\.?\s*r\.?\s*l\.?|'
        r's\.?\s*p\.?\s*a\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|'
        r's\.?\s*c\.?\s*a\.?\s*r\.?\s*l\.?|soc\.?\s*coop\.?|'
        r'unipersonale|semplificata|in\s+liquidazione)(?![a-z0-9])'
    )
    return re.sub(r'\s+', ' ', re.sub(pat, ' ', n)).strip(" .,-/").upper()

def pulisci_nome_per_linkedin(nome):
    base = pulisci_nome_azienda(nome)
    ridotto = re.sub(r'\s+', ' ', re.sub(r'(?i)\b(group|gruppo|holding)\b', '', base)).strip(" .,-/")
    # Se togliendo GROUP resta una sola parola corta/cognome (es. "BRUNO"), tiene "BRUNO GROUP" per evitare omonimi!
    if len(ridotto) < 7 and " " not in ridotto:
        return base
    return ridotto

def cerca_decision_maker_osint(nome_azienda, dominio, email_generica):
    if not serper_api_key:
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
    url = "https://google.serper.dev/search"
    azienda_pulita = pulisci_nome_azienda(nome_azienda)
    azienda_linkedin = pulisci_nome_per_linkedin(nome_azienda)
    radice_dominio = dominio.split('.')[0].replace('-', ' ').strip() if dominio else ""
    headers = {'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'}

    dominio_email = dominio
    em_gen_clean = pulisci_formato_email(email_generica)
    if email_valida(em_gen_clean):
        dom_estratto = em_gen_clean.split("@")[-1].strip().lower()
        provider_gen = {
            'gmail.com', 'libero.it', 'virgilio.it', 'alice.it', 'tin.it', 'tiscali.it',
            'hotmail.com', 'hotmail.it', 'outlook.com', 'outlook.it', 'yahoo.com', 'yahoo.it',
            'icloud.com', 'email.it', 'azienda.it', 'dominio.it', 'esempio.it', 'example.com',
            'info.com', 'info.it', 'test.it', 'pcert.it', 'arubapec.it', 'legalmail.it',
            'pec.it', 'postecert.it', 'manstar.org', 'xing.com', 'jimdoweb.com', 'webnode.it', 'webnode.page'
        }
        escl_d = ('pec', 'cert', 'legalmail', 'jimdo', 'webnode', 'wixsite')
        if dom_estratto and dom_estratto not in provider_gen and not any(p in dom_estratto for p in escl_d):
            dominio_email = dom_estratto

    try:
        # Costruisce il filtro identità combinando Ragione Sociale + Dominio + Brand da dominio (es. "GS" + "bvbitalia.com")
        termini_az = [f'"{azienda_linkedin}"']
        if dominio:
            termini_az.append(f'"{dominio}"')
        if radice_dominio and len(radice_dominio) >= 4 and radice_dominio.upper() != azienda_linkedin:
            termini_az.append(f'"{radice_dominio}"')
        blocco_identita = "(" + " OR ".join(dict.fromkeys(termini_az)) + ")"

        # Esegue SEMPRE sia la query LinkedIn sia la query Web/Dominio (senza fermarsi su falsi omonimi di q1!)
        q_linkedin_ruoli = (
            f'site:linkedin.com/in {blocco_identita} '
            f'(Commerciale OR Vendite OR Sales OR Direttore OR HR OR CEO OR Titolare OR Amministratore OR Socio OR Owner OR Founder)'
        )
        q_web_dominio = (
            f'("{dominio}" OR "{azienda_pulita}") '
            f'("Direttore Commerciale" OR "Responsabile Vendite" OR "Responsabile Commerciale" OR '
            f'"Amministratore Unico" OR "Amministratore Delegato" OR "Legale Rappresentante" OR "Titolare" OR "CEO" OR "Presidente")'
        )

        risultati_uniti = []
        link_visti = set()

        for q in (q_linkedin_ruoli, q_web_dominio):
            res = requests.post(url, headers=headers, data=json.dumps({"q": q, "gl": "it", "hl": "it"}), timeout=10)
            if res.status_code == 200:
                for item in res.json().get('organic', [])[:7]:
                    lnk = item.get('link', '')
                    if lnk not in link_visti:
                        link_visti.add(lnk)
                        risultati_uniti.append(item)

        # Fallback largo su LinkedIn solo se le prime due non hanno trovato nulla
        if not risultati_uniti:
            q_broad = f'site:linkedin.com/in {blocco_identita}'
            res_b = requests.post(url, headers=headers, data=json.dumps({"q": q_broad, "gl": "it", "hl": "it"}), timeout=10)
            if res_b.status_code == 200:
                risultati_uniti = res_b.json().get('organic', [])[:8]

        if not risultati_uniti:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"

        testo_risultati = "\n".join(
            [f"- {r.get('title')}: {r.get('snippet')} ({r.get('link', '')})" for r in risultati_uniti[:12]]
        )
        prompt = f"""Sei un software CRM B2B per ricerca agenti di commercio. NON inserire disclaimer o intestazioni.
Analizza questi risultati pubblici per l'azienda '{azienda_pulita}' (sito ufficiale: {dominio}). Dominio email: '{dominio_email}'.
ATTENZIONE AGLI OMONIMI: Seleziona SOLO una persona realmente collegata a '{azienda_pulita}' o al dominio '{dominio}' (o brand '{radice_dominio}'). Ignora omonimi di altre aziende o altri settori.

Individua UN referente reale seguendo questa priorita:
1. Coordinamento Rete Vendita: Direttore Commerciale, Responsabile Vendite, Sales Director, Head of Sales, Sales Manager, Export Manager.
2. HR: HR Manager, Responsabile Risorse Umane, Talent Acquisition.
3. Vertice / Proprieta: Amministratore Delegato, Amministratore Unico, Legale Rappresentante, CEO, Titolare, Presidente, Socio, Owner, Founder.
ESCLUSIONI: NON selezionare Area Manager, Capo Area, District Manager o Zone Manager. Preferisci sempre il Direttore Commerciale al CEO.
Costruisci email: nome.cognome@{dominio_email} (tutto attaccato minuscolo, SENZA SPAZI anche nei doppi nomi, es. gianalberto.rossi@{dominio_email}).
Rispondi SU UNA SOLA RIGA senza intestazione: NOME COGNOME | RUOLO | EMAIL
Se assente scrivi SOLO: SCONOSCIUTO | NESSUNO | NESSUNA

Risultati:
{testo_risultati}"""

        testo_risp = chiama_gemini_con_fallback(prompt, pausa_iniziale=2)
        righe_dm = [r for r in testo_risp.splitlines() if "|" in r and "NOME COGNOME" not in r.upper()]
        riga_target = (righe_dm[0] if righe_dm else testo_risp).replace("*", "").replace("Nome:", "").replace("Ruolo:", "").replace("Email:", "")
        parti = riga_target.split('|')
        nome_dm = parti[0].strip() if len(parti) > 0 else "SCONOSCIUTO"
        ruolo_dm = parti[1].strip() if len(parti) > 1 else "NESSUNO"
        email_dm = pulisci_formato_email(parti[2]) if len(parti) > 2 else "NESSUNA"
        if "SCONOSCIUTO" in nome_dm.upper() or len(nome_dm) < 3 or " " not in nome_dm:
            return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
        return nome_dm, ruolo_dm, email_dm
    except Exception as e_dm:
        print(f"Errore referente per {azienda_pulita}: {e_dm}")
        return "SCONOSCIUTO", "NESSUNO", "NESSUNA"
