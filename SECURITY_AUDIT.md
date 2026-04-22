# SECURITY AUDIT
> Bezpečnostní prověrka před vystavením na internet a na vyžádání.  
> Blocker pravidla viz `PROJECT_INSTRUCTIONS.md`.  
> **Pouze report — žádné změny bez souhlasu.**

---

## SPUŠTĚNÍ
- **Automaticky:** součást `PRE-DEPLOY START` před nasazením na internet
- **Manuálně:** příkazem `SECURITY AUDIT START`
- **Povinně:** před každým novým portem nebo endpointem

---

## STUPNĚ ZÁVAŽNOSTI

| Stupeň | Akce |
|--------|------|
| 🔴 KRITICKÉ | BLOCKER — nasazení zastaveno, viz `PROJECT_INSTRUCTIONS.md` |
| 🟠 VYSOKÉ | WARNING — opravit před nasazením |
| 🟡 STŘEDNÍ | WARNING — opravit v dalším sprintu |
| 🟢 NÍZKÉ | Zaznamenat, opravit při příležitosti |

---

## 1. CREDENTIALS A SECRETS

### 1.1 Kód a konfigurace
| Typ | Soubor | Řádek | Závažnost | Stav |
|-----|--------|-------|-----------|------|
| API klíč | ... | ... | 🔴 | ⛔/✅ |
| Token | ... | ... | 🔴 | ⛔/✅ |
| Heslo | ... | ... | 🔴 | ⛔/✅ |
| Connection string | ... | ... | 🔴 | ⛔/✅ |

### 1.2 n8n Credentials
- [ ] Všechna hesla uložena jako n8n Credentials objekt (ne plaintext v nodu)?
- [ ] n8n Credentials nejsou součástí exportovaného workflow JSON v repozitáři?
- [ ] API klíče pro placené služby (OpenAI, Stripe aj.) jsou v n8n Credentials?

### 1.3 Git historie
- [ ] `.env` byl někdy commitnutý? **ANO / NE**
  - Pokud ANO → rotovat všechny klíče + spustit `git filter-repo` nebo BFG Repo-Cleaner
- [ ] Git log neobsahuje žádné secrets? **ANO / NE**

### 1.4 Placené služby
| Služba | Klíč v kódu | Klíč v .env / n8n | Endpoint chráněn | Rate limit | Závažnost |
|--------|------------|-------------------|-----------------|------------|-----------|
| OpenAI / AI API | ANO/NE | ANO/NE | ANO/NE | ANO/NE | 🔴 |
| Stripe / platby | ANO/NE | ANO/NE | ANO/NE | ANO/NE | 🔴 |
| Jiné | ANO/NE | ANO/NE | ANO/NE | ANO/NE | 🔴 |

---

## 2. DOCKER A SÍŤOVÁ KONFIGURACE

### 2.1 Porty v docker-compose.yml
| Kontejner | Port | Binding | Má být veřejný | Závažnost |
|-----------|------|---------|---------------|-----------|
| DB | 5432/3306 | 0.0.0.0/127.0.0.1 | NE | 🔴 |
| Redis | 6379 | 0.0.0.0/127.0.0.1 | NE | 🔴 |
| n8n | 5678 | 0.0.0.0/127.0.0.1 | pouze přes reverse proxy | 🟠 |
| App | ... | ... | ... | ... |

- [ ] Všechny DB porty jsou na `127.0.0.1` (ne `0.0.0.0`)?
- [ ] n8n není přístupný přímo — pouze přes reverse proxy (nginx/Traefik)?
- [ ] Kontejnery komunikují přes interní Docker síť?

### 2.2 Docker image
- [ ] Žádný image neběží jako root (USER direktiva nastavena)?
- [ ] Image jsou z důvěryhodných zdrojů (Docker Hub official / verified)?
- [ ] Image verze jsou pinnuté (ne `:latest` v prod)?

### 2.3 Volumes
- [ ] Volumes neobsahují citlivá data bez šifrování?
- [ ] Oprávnění složek na Synology jsou restriktivní (ne 777)?

---

## 3. SYNOLOGY NAS

- [ ] Synology DSM je aktuální?
- [ ] SSH přístup na Synology je omezen na konkrétní IP (ne 0.0.0.0)?
- [ ] Výchozí admin účet je deaktivován?
- [ ] 2FA je aktivní na Synology admin účtu?
- [ ] Synology firewall blokuje porty které nejsou potřeba?
- [ ] Záloha NAS je aktivní a ověřená?
- [ ] Volné místo > 10%? (aktuální: ___ GB)

---

## 4. WEBOVÉ ROZHRANÍ A ENDPOINTY

### 4.1 Inventář endpointů
| Endpoint | Metoda | Autentizace | Volá placenou službu | Rate limit | Závažnost |
|----------|--------|-------------|---------------------|------------|-----------|
| /api/... | GET/POST | ANO/NE | ANO/NE | ANO/NE | 🔴/🟠/🟡 |

### 4.2 n8n Webhooky
| Webhook URL | Autentizace | Veřejný | Volá placenou službu | Závažnost |
|------------|-------------|---------|---------------------|-----------|
| /webhook/... | ANO/NE | ANO/NE | ANO/NE | 🔴/🟠 |

- [ ] n8n webhooky které jsou veřejné mají alespoň header token autentizaci?
- [ ] Webhook URL nejsou předvídatelné (žádné `/webhook/test`)?

### 4.3 Ochrana
- [ ] CORS nastaven restriktivně (ne `*`)?
- [ ] Rate limiting na endpointy volající AI nebo platby?
- [ ] Všechny vstupy jsou validovány na serveru?
- [ ] HTTPS aktivní, HTTP přesměrováno?

---

## 5. VEKTOROVÁ DATABÁZE

- [ ] Přístup chráněn autentizací? **ANO / NE**
- [ ] Port není otevřen přímo na internet? **ANO / NE**
- [ ] Připojení přes šifrovaný kanál (TLS)? **ANO / NE**
- [ ] Read/write přístup je omezen na aplikační server? **ANO / NE**
- [ ] Data jsou zálohována? **ANO / NE**

---

## 6. AUTENTIZACE A SESSION

- [ ] Session tokeny se invalidují po odhlášení?
- [ ] Cookies mají `HttpOnly`, `Secure`, `SameSite`?
- [ ] JWT podepsány silným algoritmem (RS256 / ES256)?
- [ ] Tokeny nejsou v localStorage?
- [ ] Přihlášení má ochranu proti brute force (rate limit / lockout)?

---

## 7. MINIMÁLNÍ PODMÍNKY PRO INTERNET ⛔
> Pokud není splněno → systém nesmí být vystaven. Viz blocker pravidla v `PROJECT_INSTRUCTIONS.md`.

- [ ] Žádný secret není hardcoded v kódu nebo n8n nodu
- [ ] `.env` není v gitu
- [ ] DB porty jsou na `127.0.0.1`
- [ ] Vektorová DB je za autentizací
- [ ] Endpointy volající placené služby jsou za přihlášením
- [ ] Rate limiting na AI/platební endpointy existuje
- [ ] HTTPS aktivní
- [ ] n8n přístupný pouze přes reverse proxy

**Splněno:** ANO / NE  
**Nesplněné body:** seznam

---

## VÝSTUPNÍ REPORT (generuje AI)

```
DATUM: ___
BLOCKER POLOŽKY: počet nebo "žádné"
VYSOKÉ WARNINGY: seznam nebo "žádné"
MINIMÁLNÍ PODMÍNKY PRO INTERNET: SPLNĚNY / NESPLNĚNY
LZE POKRAČOVAT K NASAZENÍ: ANO / NE
```

---
*Verze: 2.0 | Stack: n8n + Docker + Synology*
