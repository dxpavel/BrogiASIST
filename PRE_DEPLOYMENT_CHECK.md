# PRE-DEPLOYMENT CHECK
> Spustit před každou změnou v prod.  
> Blocker pravidla viz `PROJECT_INSTRUCTIONS.md`.  
> **Žádná změna dokud není report odsouhlasený.**

---

## REŽIM SPUŠTĚNÍ

| Příkaz | Co se spustí | Kdy |
|--------|-------------|-----|
| `PRE-DEPLOY START` | Sekce 1–9 | Každá prod změna |
| `HOTFIX START` | Sekce 1, 3, 5, 6, 7, 9 | Urgentní oprava |

---

## 1. POPIS ZMĚNY

- **Prostředí:** dev / staging / prod
- **Soubory / workflow / kontejner:** seznam
- **Typ změny:** nová funkce / oprava / konfigurace / upgrade

---

## 2. CODE AUDIT (přeskočit při HOTFIX)
> Podrobný výstup viz `CODE_AUDIT.md`.

- [ ] Dead code audit proběhl?
- [ ] Nalezené položky zaznamenány?
- [ ] Žádná položka neblokuje nasazení?

---

## 3. PROMĚNNÉ A SECRETS

### Kód a .env
- [ ] Žádný API klíč nebo token není hardcoded v kódu?
- [ ] `.env` není commitnutý do gitu?
- [ ] Všechny nové proměnné jsou v `.env.example`?

### n8n specifika
- [ ] Všechna hesla a tokeny v n8n jsou uloženy jako **Credentials objekt** (ne plaintext v nodu)?
- [ ] Žádná hardcoded URL v n8n nodu (použity env proměnné)?
- [ ] n8n Credentials nejsou exportovány do veřejného repozitáře?

### Inventář nových proměnných
| Proměnná | Zdroj | Cíl | Uložena v | Stav |
|----------|-------|-----|-----------|------|
| ...      | ...   | ... | .env / n8n Credentials / kód | ✅/❌ |

---

## 4. MODULY A WORKFLOW (přeskočit při HOTFIX)

### Dopad změny
| Modul / Workflow | Zasažen | Typ | Riziko |
|-----------------|---------|-----|--------|
| ...             | ANO/NE  | přímý/nepřímý | NÍZKÉ/STŘEDNÍ/VYSOKÉ |

### n8n workflow
- [ ] Změněný workflow má aktivní error handler?
- [ ] Všechny HTTP Request nody mají nastaven timeout?
- [ ] Změna neovlivňuje jiné aktivní workflow (trigger kolize)?

---

## 5. DOCKER A KONTEJNERY

### docker-compose.yml
- [ ] DB porty jsou bindovány na `127.0.0.1` (ne `0.0.0.0`)?
- [ ] Každý kontejner má definovaný `restart: unless-stopped`?
- [ ] Každý kontejner má `healthcheck`?
- [ ] Image verze jsou pinnuté (ne `:latest` v prod)?

### Volumes a persistence
- [ ] Každý kontejner s daty má namapovaný volume na Synology?
- [ ] Cesta volume na Synology existuje a je přístupná?
- [ ] Při smazání kontejneru data přežijí (volume není anonymní)?

| Kontejner | Volume | Cesta na Synology | Persistence ověřena |
|-----------|--------|-------------------|---------------------|
| ...       | ...    | ...               | ANO/NE |

### Sítě
- [ ] Kontejnery komunikují přes interní Docker síť (ne přes host)?
- [ ] Pouze nutné porty jsou vystaveny ven?

---

## 6. DATABÁZE

### Operace
| DB / Kolekce | Operace | Kdo volá | WHERE podmínka | Riziko |
|-------------|---------|----------|---------------|--------|
| ...         | R/W/D   | ...      | ANO/NE        | ... |

### Kontrola
- [ ] Žádný DELETE nebo UPDATE bez WHERE podmínky?
- [ ] Změna schématu má migration script?
- [ ] Migration script je reversibilní (rollback)?
- [ ] Záloha DB před nasazením provedena?

---

## 7. SYNOLOGY A DISK

- [ ] Volné místo na disku > 10%? (aktuální stav: ___ GB volných)
- [ ] Nový Docker image se vejde na disk?
- [ ] Záloha Synology je aktuální (ne starší než 24h)?
- [ ] Oprávnění složek jsou správně nastavena (ne 777)?

---

## 8. DESTRUKTIVNÍ OPERACE ⛔ BLOCKER

- [ ] Obsahuje změna `DELETE` bez WHERE? **ANO / NE**
- [ ] Obsahuje změna `DROP TABLE` nebo `DROP DATABASE`? **ANO / NE**
- [ ] Maže změna Docker volume s daty? **ANO / NE**
- [ ] Přepisuje změna existující soubory bez zálohy? **ANO / NE**
- [ ] Mění změna produkční `.env`? **ANO / NE**

**Výsledek blokeru:** ✅ PRŮCHOD / ⛔ ZASTAVENO — důvod: ___

---

## 9. ROLLBACK PLÁN

- **Jak vrátit změnu:** popis kroků
- **Git commit / tag před nasazením:** hash
- **Docker image před nasazením:** název:tag
- **Záloha DB:** ANO / NE / NENÍ TŘEBA
- **Čas potřebný k rollbacku:** odhad

---

## VÝSTUPNÍ REPORT (generuje AI)

```
DATUM: ___
PROSTŘEDÍ: prod
POPIS ZMĚNY: ___
BLOCKER: ✅ PRŮCHOD / ⛔ ZASTAVENO — důvod: ___
WARNINGY: seznam nebo "žádné"
LZE POKRAČOVAT K NASAZENÍ: ANO / NE
```

---
*Verze: 2.0 | Stack: n8n + Docker + Synology*
