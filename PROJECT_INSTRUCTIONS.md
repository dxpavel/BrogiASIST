# PROJECT INSTRUCTIONS
> Vložit do Project Instructions v nastavení projektu.  
> Platí automaticky pro každý chat v projektu.

---

## STACK
- **Workflow:** n8n
- **Kontejnerizace:** Docker / Docker Compose
- **Úložiště:** Synology NAS
- **Prostředí:** dev / staging / prod

---

## PŘÍKAZY

| Příkaz | Akce |
|--------|------|
| `PRE-DEPLOY START` | Kompletní checklist před změnou (prod) |
| `HOTFIX START` | Zrychlený checklist — přeskočí CODE_AUDIT, zachová SECURITY |
| `AUDIT START` | Code audit (dead code, duplicity, pozůstatky) |
| `SECURITY AUDIT START` | Bezpečnostní audit |
| `FULL CHECK` | Všechny tři audity najednou |

---

## AUTOMATICKÉ SPUŠTĚNÍ

| Situace | Spustit |
|---------|---------|
| Každá změna v prod | `PRE-DEPLOY START` |
| Urgentní oprava | `HOTFIX START` |
| Větší refactor | `FULL CHECK` |
| Nový port nebo endpoint | `SECURITY AUDIT START` |
| Změna docker-compose.yml | `PRE-DEPLOY START` + `SECURITY AUDIT START` |

---

## PROSTŘEDÍ

| Prostředí | Účel | Nasazení |
|-----------|------|---------|
| dev | vývoj, testování | volně, bez checku |
| staging | ověření před prod | PRE-DEPLOY bez blocker zastavení |
| prod | produkce | plný PRE-DEPLOY, blocker zastavuje |

---

## BLOCKER PRAVIDLA ⛔
> Definováno zde — nikde jinde. Ostatní soubory odkazují sem.

Nasazení do **prod** se automaticky zastavuje pokud:

- API klíč, token nebo heslo je hardcoded v kódu nebo n8n nodu
- `.env` je commitnutý do gitu
- `docker-compose.yml` vystavuje DB port na `0.0.0.0` místo `127.0.0.1`
- n8n workflow obsahuje plaintext credentials místo Credentials objektu
- Synology volume není namapován (kontejner bez persistence)
- Endpoint volající placenou službu není za autentizací
- Volné místo na disku < 10% (Synology)
- Chybí rollback plán

---

## WARNING PRAVIDLA ⚠️
> Zaznamenat, nevyžadovat zastavení — opravit v dalším sprintu.

- Chybí rate limiting na AI/platební endpointy
- Zastaralé Docker image (starší než 90 dní)
- Chybí healthcheck v docker-compose.yml
- n8n workflow nemá error handler
- Logy obsahují citlivé informace

---

## VÝSTUPNÍ FORMÁT KAŽDÉHO REPORTU

```
DATUM: ___
PROSTŘEDÍ: dev / staging / prod
POPIS ZMĚNY: ___
BLOCKER: ✅ PRŮCHOD / ⛔ ZASTAVENO — důvod: ___
WARNINGY: seznam nebo "žádné"
LZE POKRAČOVAT K NASAZENÍ: ANO / NE
```

> Report generuje AI automaticky ve formátu výše.  
> Pavel pouze potvrdí nebo zamítne.

---

## REFERENCE
- `PRE_DEPLOYMENT_CHECK.md` — checklist před změnou
- `CODE_AUDIT.md` — dead code, duplicity, pozůstatky
- `SECURITY_AUDIT.md` — bezpečnostní audit

---
*Verze: 2.0 | Stack: n8n + Docker + Synology*
